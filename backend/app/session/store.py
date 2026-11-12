"""会话与消息模型 + 内存会话仓库。

一个 Session 就是前端的一个窗口：消息、待办、摘要、压缩游标都挂在它上面，
因此不同窗口之间天然互不影响。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.common.errors import ToolError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Message:
    role: str  # user | assistant | tool
    content: str  # user 原文 / assistant 的 LLM 原始输出 / tool 的结果 JSON
    text: str = ""  # 给人看的内容（前端只渲染它，不解析协议）
    thought: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_ok: bool = True
    trace: list = field(default_factory=list)  # 仅最终 assistant 消息：本轮完整步骤
    visible: bool = True  # 中间步骤消息进上下文但不进 UI
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "text": self.text,
            "thought": self.thought,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_ok": self.tool_ok,
            "trace": self.trace,
            "visible": self.visible,
            "created_at": self.created_at,
        }


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    title: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    messages: list[Message] = field(default_factory=list)
    summary: str = ""  # 压缩后的早期内容摘要
    compressed_upto: int = 0  # messages[:compressed_upto] 已压进 summary
    state: dict[str, Any] = field(default_factory=dict)  # 工具私有状态（如 todos）
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def add(self, message: Message) -> Message:
        self.messages.append(message)
        self.updated_at = now_iso()
        if not self.title and message.role == "user":
            self.title = (message.text or message.content).strip()[:20] or "新会话"
        return message

    @property
    def todos(self) -> list[dict]:
        return self.state.setdefault("todos", [])

    def visible_messages(self) -> list[Message]:
        return [m for m in self.messages if m.visible]

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title or "新会话",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.visible_messages()),
        }

    def to_detail_dict(self) -> dict:
        return {
            **self.to_summary_dict(),
            "summary": self.summary,
            "messages": [m.to_dict() for m in self.visible_messages()],
            "todos": self.todos,
        }


class SessionStore:
    """单进程内存仓库。重启即清空，是本项目的刻意取舍（见 README）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, title: str = "") -> Session:
        session = Session(title=title)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise ToolError(f"会话不存在：{session_id}")
        return session

    def list(self) -> list[dict]:
        sessions = sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
        return [s.to_summary_dict() for s in sessions]

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def clear(self) -> None:
        self._sessions.clear()
