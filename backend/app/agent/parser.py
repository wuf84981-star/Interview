"""LLM 输出解析器：从自由文本中稳定提取 思考 / 工具调用 / 最终答案。

容错顺序：原样 → 去 markdown 代码围栏 → 括号平衡扫描子串 → 判定 invalid。
解析器只负责「结构化」，不做重试；重试策略在主循环里。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_MAX_OBJECT_SCAN = 3


@dataclass
class ParsedOutput:
    kind: str  # final | action | invalid
    thought: str = ""
    action: str = ""
    action_input: dict = field(default_factory=dict)
    final_answer: str = ""
    raw: str = ""
    error: str = ""


def _balanced_objects(text: str, limit: int = _MAX_OBJECT_SCAN) -> list[str]:
    """扫描出括号平衡的 JSON 对象子串（能跳过字符串里的括号与转义）。"""
    found: list[str] = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    found.append(text[start : index + 1])
                    break
        if len(found) >= limit:
            break
    return found


def _candidates(raw: str) -> list[str]:
    text = raw.strip()
    items = [text]
    items.extend(match.group(1).strip() for match in _FENCE_RE.finditer(text))
    items.extend(_balanced_objects(text))
    # 去重且保序
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _normalize(data: dict, raw: str) -> ParsedOutput:
    thought = str(data.get("thought", "") or "").strip()
    final_answer = data.get("final_answer")
    if isinstance(final_answer, str) and final_answer.strip():
        return ParsedOutput(kind="final", thought=thought, final_answer=final_answer.strip(), raw=raw)

    action = data.get("action")
    if isinstance(action, str) and action.strip():
        action_input = data.get("action_input", {})
        if isinstance(action_input, str):  # 有些模型会把参数序列化成字符串
            try:
                action_input = json.loads(action_input)
            except json.JSONDecodeError:
                action_input = {}
        if not isinstance(action_input, dict):
            action_input = {}
        return ParsedOutput(
            kind="action",
            thought=thought,
            action=action.strip(),
            action_input=action_input,
            raw=raw,
        )

    return ParsedOutput(kind="invalid", thought=thought, raw=raw, error="JSON 中缺少 action 或 final_answer 字段")


def parse_llm_output(raw: str) -> ParsedOutput:
    if not raw or not raw.strip():
        return ParsedOutput(kind="invalid", raw=raw, error="模型返回了空内容")

    last_error = "输出不是合法的 JSON 对象"
    for candidate in _candidates(raw):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = f"JSON 解析失败：{exc.msg if hasattr(exc, 'msg') else exc}"
            continue
        if isinstance(data, dict):
            return _normalize(data, raw)
        last_error = "输出不是 JSON 对象"

    return ParsedOutput(kind="invalid", raw=raw, error=last_error)
