"""测试与演示用的假模型（不产生任何网络调用）。

- ScriptedLLM：按预置脚本逐条返回，测试用它精确控制 Agent 的每一步决策。
- RuleBasedLLM：极简规则模型，LLM_MOCK=1 时无需任何 API Key 即可跑通完整链路。
"""

from __future__ import annotations

import json
import re

from app.common.errors import LLMError
from app.tools.weather import WEATHER_DB

_CITY_NAMES = list(WEATHER_DB)

WEEKLY_REPORT = (
    "本周周报草稿：\n"
    "1. 进展：完成 MiniAgent 主循环与工具注册机制；\n"
    "2. 下周计划：补齐上下文压缩与会话隔离的测试；\n"
    "3. 风险：模型输出格式仍偶有波动，已加入解析重试。"
)


def _dumps(thought: str, **kwargs) -> str:
    return json.dumps({"thought": thought, **kwargs}, ensure_ascii=False)


class ScriptedLLM:
    """按顺序吐出预设响应；同时记录每次收到的上下文，便于断言「模型看到了什么」。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    async def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if not self._responses:
            raise LLMError("ScriptedLLM 的脚本已用尽")
        return self._responses.pop(0)


class RuleBasedLLM:
    """关键词规则模型：够用来演示「决策 → 工具 → 收敛」的完整链路。"""

    async def complete(self, messages: list[dict]) -> str:
        last = messages[-1]["content"]
        if last.startswith("Observation("):
            return self._after_observation(messages)
        return self._decide(last)

    # ---------- 决策 ----------
    def _after_observation(self, messages: list[dict]) -> str:
        """已经调过一个工具后：先看还有没有没做完的子任务，否则收敛。"""
        request = self._turn_request(messages)
        used = [
            message["content"].split("(")[1].split(")")[0]
            for message in messages
            if message["content"].startswith("Observation(")
        ]
        if "待办" in request and "todo" not in used:
            return _dumps(
                "主任务已完成，还有待办要记，继续调用 todo",
                action="todo",
                action_input={"action": "add", "content": self._extract_todo(request)},
            )
        if "周报" in request:
            return _dumps(
                "待办已记下，现在给出周报草稿",
                final_answer=WEEKLY_REPORT + "\n\n（已顺便记入待办）",
            )
        return self._from_observation(messages[-1]["content"])

    def _decide(self, text: str) -> str:
        for city in _CITY_NAMES:
            if city in text and "天气" in text:
                return _dumps(f"用户想知道{city}的天气，调用 weather",
                              action="weather", action_input={"city": city})

        if "天气" in text:
            return _dumps("缺少城市信息，先向用户确认",
                          final_answer="请告诉我你想查询哪个城市的天气。")

        expression = self._extract_expression(text)
        if expression:
            return _dumps("这是一个数学计算，调用 calculator",
                          action="calculator", action_input={"expression": expression})

        # 待办优先于周报：保证「写周报，顺便记个待办」里的待办不会漏掉
        if "待办" in text:
            asking = any(word in text for word in ("什么", "哪些", "多少", "查看", "看看", "列", "？", "?"))
            adding = any(word in text for word in ("记", "添加", "新增", "加"))
            if adding and not asking:
                return _dumps("用户要新增待办，调用 todo",
                              action="todo",
                              action_input={"action": "add", "content": self._extract_todo(text)})
            return _dumps("用户要查看待办，调用 todo", action="todo", action_input={"action": "list"})

        if "周报" in text:
            return _dumps("用户要写周报，直接给出结构化草稿", final_answer=WEEKLY_REPORT)

        if any(word in text for word in ("搜索", "查一下", "检索")):
            return _dumps("需要检索本地知识库，调用 search",
                          action="search", action_input={"query": text})

        return _dumps("这是普通对话，直接回复", final_answer=f"（Mock 模型）收到：{text}")

    # ---------- 解释工具结果 ----------
    def _from_observation(self, text: str) -> str:
        match = re.match(r"Observation\(([^)]+)\):\s*(\{.*\})", text, re.S)
        if not match:
            return _dumps("工具结果无法理解，如实告知", final_answer="工具返回了无法解析的结果。")
        tool, payload_text = match.group(1), match.group(2)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return _dumps("工具结果无法解析，如实告知", final_answer="工具返回了无法解析的结果。")

        if isinstance(payload, dict) and payload.get("error"):
            return _dumps("工具调用失败，如实告知用户",
                          final_answer=f"调用 {tool} 时出错：{payload['error']}")

        if tool == "weather":
            return _dumps(
                "已取得天气数据，整理后回答",
                final_answer=(
                    f"{payload['city']}今天{payload['condition']}，气温 {payload['temp']}，"
                    f"湿度 {payload['humidity']}，{payload['wind']}。"
                ),
            )
        if tool == "calculator":
            return _dumps("已算出结果，直接回答",
                          final_answer=f"{payload['expression']} = {payload['result']}")
        if tool == "todo":
            todos = payload.get("todos", [])
            if not todos:
                return _dumps("待办为空，直接回答", final_answer="当前没有任何待办事项。")
            lines = [f"{item['id']}. [{'x' if item['done'] else ' '}] {item['content']}" for item in todos]
            return _dumps("已取得待办列表，整理后回答", final_answer="当前待办：\n" + "\n".join(lines))
        if tool == "search":
            results = payload.get("results", [])
            if not results:
                return _dumps("没有检索到结果，直接回答", final_answer="本地知识库里没有找到相关内容。")
            lines = [f"- {item['title']}：{item['snippet']}" for item in results]
            return _dumps("已取得检索结果，整理后回答", final_answer="为你找到这些资料：\n" + "\n".join(lines))

        return _dumps("已取得工具结果", final_answer=json.dumps(payload, ensure_ascii=False))

    # ---------- 小工具 ----------
    @staticmethod
    def _turn_request(messages: list[dict]) -> str:
        """找出本轮用户的原始请求（跳过 Observation 回灌的伪 user 消息）。"""
        for message in reversed(messages):
            if message["role"] == "user" and not message["content"].startswith("Observation("):
                return message["content"]
        return ""

    @staticmethod
    def _extract_expression(text: str) -> str:
        for chunk in re.findall(r"[0-9][0-9\.\s\+\-\*/%\(\)]*", text):
            candidate = chunk.strip()
            if any(op in candidate for op in "+-*/%") and re.search(r"\d", candidate):
                return candidate.rstrip("+ - * / %")
        return ""

    @staticmethod
    def _extract_todo(text: str) -> str:
        cleaned = re.sub(
            r"帮我|请|把|一下|记录|记|添加|新增|到|待办|事项|一个|一条|然后|接着|再", "", text
        )
        cleaned = cleaned.strip(" ，,。:：、")
        return cleaned or text
