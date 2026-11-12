"""上下文组装与压缩。

memory 的召回时机：主循环的每一步都重新组装一次，所以工具结果能被下一步立刻看到；
压缩时机：每轮对话开始前，若未压缩部分超出预算就把旧消息压成摘要。
"""

from __future__ import annotations

import json

from app.agent.prompt import render_observation
from app.config import Settings
from app.session.store import Message, Session

MAX_MESSAGES = 24  # 未压缩消息条数上限
CLIP_USER = 60
CLIP_TOOL = 60


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def build_context(session: Session, system_prompt: str) -> list[dict]:
    """按「系统提示 → 摘要 → 最近消息」的顺序拼出本轮上下文。"""
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if session.summary:
        messages.append(
            {
                "role": "system",
                "content": "以下是本会话较早内容的摘要（原文已压缩，仅保留要点）：\n" + session.summary,
            }
        )

    for message in session.messages[session.compressed_upto :]:
        if message.role == "user":
            messages.append({"role": "user", "content": message.content})
        elif message.role == "assistant":
            messages.append({"role": "assistant", "content": message.content})
        elif message.role == "tool":
            messages.append(
                {"role": "user", "content": render_observation(message.tool_name, message.content)}
            )
    return messages


def _digest(message: Message) -> str:
    if message.role == "user":
        return f"用户: {_clip(message.content, CLIP_USER)}"
    if message.role == "assistant":
        if message.tool_name:
            args = _clip(json.dumps(message.tool_args, ensure_ascii=False), 40)
            return f"助手调用 {message.tool_name}（{args}）"
        return f"助手: {_clip(message.text or message.content, CLIP_USER)}"
    if message.role == "tool":
        status = "成功" if message.tool_ok else "失败"
        return f"工具 {message.tool_name} {status}: {_clip(message.content, CLIP_TOOL)}"
    return ""


def maybe_compress(session: Session, settings: Settings) -> int:
    """超出预算时把较老的消息压成摘要，返回被压缩的消息条数。"""
    start = session.compressed_upto
    pending = session.messages[start:]
    keep = settings.keep_recent_messages
    if len(pending) <= keep:
        return 0

    total_chars = sum(len(message.content) for message in pending)
    if total_chars <= settings.context_char_budget and len(pending) <= MAX_MESSAGES:
        return 0

    cutoff = len(session.messages) - keep
    lines: list[str] = []
    for message in session.messages[start:cutoff]:
        # 中间步骤的 assistant 原文（原始 JSON）与格式重试提示没有保留价值
        if message.role != "tool" and not message.visible:
            continue
        digest = _digest(message)
        if digest:
            lines.append(digest)

    if lines:
        merged = "\n".join([session.summary, *lines]) if session.summary else "\n".join(lines)
        merged = merged.strip()
        if len(merged) > settings.summary_max_chars:
            merged = merged[-settings.summary_max_chars :]
            newline = merged.find("\n")
            if 0 <= newline < 80:  # 尽量从整行开始，避免半截句子
                merged = merged[newline + 1 :]
        session.summary = merged

    session.compressed_upto = cutoff
    return cutoff - start
