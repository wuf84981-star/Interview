"""Agent 主循环：输入 → 决策 → 工具 → 再决策 → 收敛。

产出的是事件流（dict），由 API 层转成 SSE；错误以事件形式汇报，不抛给传输层。
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

from app.agent.context import build_context, maybe_compress
from app.agent.parser import parse_llm_output
from app.agent.prompt import REPAIR_HINT, render_system_prompt
from app.common.errors import LLMError
from app.common.logging import log_event
from app.config import Settings
from app.session.store import Message, Session
from app.tools.registry import ToolRegistry, registry as default_registry

MAX_PARSE_RETRY = 1  # 解析失败最多重试 1 次，之后降级


def _clip(text: str, limit: int = 800) -> str:
    flat = str(text).strip()
    return flat if len(flat) <= limit else flat[:limit] + "…"


class AgentRuntime:
    def __init__(
        self,
        llm,
        settings: Settings,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.tools = tools or default_registry
        self.system_prompt = render_system_prompt(self.tools.schemas(), settings.max_steps)

    async def run_turn(self, session: Session, user_text: str) -> AsyncIterator[dict]:
        """处理一轮用户输入，逐步产出事件。"""
        session.add(Message(role="user", content=user_text, text=user_text))
        yield {"event": "session", "data": {"session_id": session.id, "title": session.title}}
        log_event("turn_start", session_id=session.id, chars=len(user_text))

        dropped = maybe_compress(session, self.settings)
        if dropped:
            log_event("compress", session_id=session.id, dropped=dropped, summary_chars=len(session.summary))
            yield {
                "event": "context_compressed",
                "data": {"dropped": dropped, "summary_chars": len(session.summary)},
            }

        trace: list[dict] = []
        parse_failures = 0
        started = time.perf_counter()

        for step in range(1, self.settings.max_steps + 1):
            yield {"event": "step", "data": {"index": step}}

            messages = build_context(session, self.system_prompt)
            log_event(
                "llm_call",
                session_id=session.id,
                step=step,
                messages=len(messages),
                chars=sum(len(item["content"]) for item in messages),
            )

            try:
                raw = await self.llm.complete(messages)
            except LLMError as exc:
                log_event("llm_error", session_id=session.id, step=step, error=exc.message)
                yield {"event": "error", "data": {"message": exc.message}}
                return

            parsed = parse_llm_output(raw)

            # ---- 分支一：解析失败 → 修复重试，二次失败则降级 ----
            if parsed.kind == "invalid":
                parse_failures += 1
                log_event("parse_failed", session_id=session.id, step=step, error=parsed.error)
                trace.append({"index": step, "parse_error": parsed.error})
                yield {"event": "parse_error", "data": {"message": "模型输出格式不合法，正在要求其重试"}}

                if parse_failures > MAX_PARSE_RETRY:
                    answer = _clip(raw) or "抱歉，模型没有给出可用的回复，请重试。"
                    session.add(
                        Message(role="assistant", content=raw, text=answer, thought="", trace=trace)
                    )
                    yield {"event": "answer", "data": {"content": answer, "stopped_reason": "parse_fallback"}}
                    log_event("turn_end", session_id=session.id, stopped_reason="parse_fallback")
                    return

                session.add(Message(role="assistant", content=raw, visible=False))
                session.add(Message(role="user", content=REPAIR_HINT, visible=False))
                continue

            # ---- 分支二：直接回答 ----
            if parsed.kind == "final":
                trace.append({"index": step, "thought": parsed.thought, "final": True})
                session.add(
                    Message(
                        role="assistant",
                        content=raw,
                        text=parsed.final_answer,
                        thought=parsed.thought,
                        trace=trace,
                    )
                )
                yield {"event": "thought", "data": {"content": parsed.thought}}
                yield {
                    "event": "answer",
                    "data": {"content": parsed.final_answer, "stopped_reason": "final"},
                }
                log_event(
                    "turn_end",
                    session_id=session.id,
                    steps=step,
                    stopped_reason="final",
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return

            # ---- 分支三：调用工具，然后回到循环继续判断 ----
            thought = parsed.thought
            yield {"event": "thought", "data": {"content": thought}}
            yield {"event": "tool_call", "data": {"tool": parsed.action, "args": parsed.action_input}}

            result = self.tools.invoke(parsed.action, parsed.action_input, session)
            trace.append(
                {
                    "index": step,
                    "thought": thought,
                    "tool": result["tool"],
                    "args": parsed.action_input,
                    "ok": result["ok"],
                    "result": result["result"],
                    "elapsed_ms": result["elapsed_ms"],
                }
            )
            yield {
                "event": "observation",
                "data": {
                    "tool": result["tool"],
                    "ok": result["ok"],
                    "result": result["result"],
                    "elapsed_ms": result["elapsed_ms"],
                },
            }

            session.add(
                Message(
                    role="assistant",
                    content=raw,
                    thought=thought,
                    tool_name=parsed.action,
                    tool_args=parsed.action_input,
                    tool_ok=result["ok"],
                    visible=False,
                )
            )
            session.add(
                Message(
                    role="tool",
                    content=json.dumps(result["result"], ensure_ascii=False),
                    tool_name=result["tool"],
                    tool_ok=result["ok"],
                    visible=False,
                )
            )

        # ---- 分支四：轮次用尽 ----
        answer = (
            f"我已经连续尝试 {self.settings.max_steps} 步仍未完成这个任务。"
            "你可以补充信息，或直接说「继续」让我接着做。"
        )
        trace.append({"index": self.settings.max_steps, "stopped_reason": "max_steps"})
        session.add(
            Message(
                role="assistant",
                content=json.dumps({"thought": "达到最大轮次", "final_answer": answer}, ensure_ascii=False),
                text=answer,
                thought="达到最大轮次限制",
                trace=trace,
            )
        )
        yield {"event": "answer", "data": {"content": answer, "stopped_reason": "max_steps"}}
        log_event("turn_end", session_id=session.id, stopped_reason="max_steps")
