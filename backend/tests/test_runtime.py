"""主循环：直接回答、单工具、多工具、异常自愈、轮次上限、解析降级。"""

import json

from app.agent.runtime import AgentRuntime
from app.config import Settings
from app.llm.mock import ScriptedLLM


def action(thought: str, name: str, **args) -> str:
    return json.dumps({"thought": thought, "action": name, "action_input": args}, ensure_ascii=False)


def final(thought: str, answer: str) -> str:
    return json.dumps({"thought": thought, "final_answer": answer}, ensure_ascii=False)


async def run(llm, session, text: str, settings: Settings | None = None):
    runtime = AgentRuntime(llm, settings or Settings(llm_mock=True))
    return [event async for event in runtime.run_turn(session, text)]


def names(events) -> list[str]:
    return [event["event"] for event in events]


def pick(events, name: str):
    return [event["data"] for event in events if event["event"] == name]


async def test_direct_answer_no_tool(session):
    llm = ScriptedLLM([final("这是寒暄", "你好，我是 MiniAgent")])
    events = await run(llm, session, "你好")

    assert names(events) == ["session", "step", "thought", "answer"]
    assert pick(events, "answer")[0]["content"] == "你好，我是 MiniAgent"
    assert pick(events, "answer")[0]["stopped_reason"] == "final"
    assert [m.role for m in session.messages] == ["user", "assistant"]


async def test_single_tool_then_answer(session):
    llm = ScriptedLLM(
        [
            action("用户问天气，调用 weather", "weather", city="深圳"),
            final("拿到结果", "深圳今天多云"),
        ]
    )
    events = await run(llm, session, "深圳天气怎么样")

    assert names(events) == [
        "session",
        "step",
        "thought",
        "tool_call",
        "observation",
        "step",
        "thought",
        "answer",
    ]
    assert pick(events, "tool_call")[0] == {"tool": "weather", "args": {"city": "深圳"}}
    assert pick(events, "observation")[0]["ok"] is True
    # 中间步骤进上下文但不进 UI
    assert [m.role for m in session.messages] == ["user", "assistant", "tool", "assistant"]
    assert [m.visible for m in session.messages] == [True, False, False, True]


async def test_two_tools_in_one_turn(session):
    llm = ScriptedLLM(
        [
            action("先查天气", "weather", city="北京"),
            action("再算温差", "calculator", expression="19-8"),
            final("都拿到了", "北京 8~19℃，温差 11 度"),
        ]
    )
    events = await run(llm, session, "北京天气怎么样，温差多少")

    calls = pick(events, "tool_call")
    assert [item["tool"] for item in calls] == ["weather", "calculator"]
    assert pick(events, "answer")[0]["stopped_reason"] == "final"
    assert len(session.messages) == 6  # user + 2×(assistant+tool) + final assistant


async def test_tool_error_does_not_break_loop(session):
    llm = ScriptedLLM(
        [
            action("查火星天气", "weather", city="火星"),
            final("查不到就如实说", "暂时没有火星的天气数据"),
        ]
    )
    events = await run(llm, session, "火星天气")

    observation = pick(events, "observation")[0]
    assert observation["ok"] is False
    assert "可查询的城市" in observation["result"]["error"]
    assert pick(events, "answer")[0]["stopped_reason"] == "final"


async def test_unknown_tool_is_reported_back(session):
    llm = ScriptedLLM([action("随便调个工具", "teleport", city="深圳"), final("改用别的说法", "做不到")])
    events = await run(llm, session, "瞬移一下")

    assert pick(events, "observation")[0]["ok"] is False
    assert "未知工具" in pick(events, "observation")[0]["result"]["error"]


async def test_max_steps_guard(session):
    llm = ScriptedLLM([action("继续查", "weather", city="深圳") for _ in range(3)])
    events = await run(llm, session, "一直查", Settings(llm_mock=True, max_steps=2))

    assert pick(events, "answer")[0]["stopped_reason"] == "max_steps"
    # 历史保留，用户可以直接追问「继续」
    assert session.messages[-1].visible is True
    assert "继续" in session.messages[-1].text


async def test_parse_failure_is_retried(session):
    llm = ScriptedLLM(["我先想想……", final("这次格式对了", "修好了")])
    events = await run(llm, session, "你好")

    assert "parse_error" in names(events)
    assert pick(events, "answer")[0]["content"] == "修好了"
    # 重试提示作为不可见消息进入上下文
    assert any(not m.visible and m.role == "user" for m in session.messages)


async def test_parse_failure_twice_falls_back_to_raw_text(session):
    llm = ScriptedLLM(["第一次格式错", "第二次还是错的"])
    events = await run(llm, session, "你好")

    answer = pick(events, "answer")[0]
    assert answer["stopped_reason"] == "parse_fallback"
    assert answer["content"] == "第二次还是错的"


async def test_llm_error_is_reported_as_event(session):
    llm = ScriptedLLM([])  # 脚本为空 → 直接抛 LLMError
    events = await run(llm, session, "你好")

    assert "error" in names(events)
    assert "answer" not in names(events)
    # 用户消息仍然保留，可以重发
    assert session.messages[-1].role == "user"
