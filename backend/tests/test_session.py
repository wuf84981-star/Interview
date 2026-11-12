"""会话隔离与追问：两个窗口互不影响，历史可连续。"""

import json

from app.agent.runtime import AgentRuntime
from app.config import Settings
from app.llm.mock import ScriptedLLM


def action(name: str, **args) -> str:
    return json.dumps({"thought": "调工具", "action": name, "action_input": args}, ensure_ascii=False)


def final(answer: str) -> str:
    return json.dumps({"thought": "回答", "final_answer": answer}, ensure_ascii=False)


async def collect(runtime, session, text):
    return [event async for event in runtime.run_turn(session, text)]


def visible_text(session) -> str:
    return " ".join(message.text for message in session.visible_messages())


async def test_two_sessions_are_isolated(store):
    window1, window2 = store.create(), store.create()

    runtime1 = AgentRuntime(ScriptedLLM([action("weather", city="深圳"), final("深圳多云")]), Settings(llm_mock=True))
    await collect(runtime1, window1, "窗口1：查深圳天气")

    runtime2 = AgentRuntime(ScriptedLLM([final("周报写好了")]), Settings(llm_mock=True))
    await collect(runtime2, window2, "窗口2：写周报")

    assert "窗口1" in visible_text(window1) and "窗口1" not in visible_text(window2)
    assert "窗口2" in visible_text(window2) and "窗口2" not in visible_text(window1)


async def test_follow_up_sees_previous_turn(store):
    session = store.create()
    llm = ScriptedLLM([final("深圳今天多云"), final("北京今天晴")])
    runtime = AgentRuntime(llm, Settings(llm_mock=True))

    await collect(runtime, session, "深圳天气怎么样")
    await collect(runtime, session, "那北京呢")

    # 第二轮送给模型的上下文里必须包含第一轮的用户问题与回答
    second_context = llm.calls[1]
    joined = " ".join(item["content"] for item in second_context)
    assert "深圳天气怎么样" in joined
    assert "深圳今天多云" in joined
    assert "那北京呢" in joined


async def test_follow_up_with_tool_keeps_state(store):
    session = store.create()
    llm = ScriptedLLM(
        [
            action("todo", action="add", content="买牛奶"),
            final("记好了"),
            action("todo", action="list"),
            final("你有一条待办"),
        ]
    )
    runtime = AgentRuntime(llm, Settings(llm_mock=True))

    await collect(runtime, session, "帮我记一个待办：买牛奶")
    events = await collect(runtime, session, "我有哪些待办")

    observation = [event["data"] for event in events if event["event"] == "observation"][0]
    assert observation["result"]["count"] == 1
    assert observation["result"]["todos"][0]["content"] == "买牛奶"


async def test_title_comes_from_first_user_message(store):
    session = store.create()
    runtime = AgentRuntime(ScriptedLLM([final("好的")]), Settings(llm_mock=True))
    await collect(runtime, session, "帮我整理一下本周的工作计划并写周报")
    assert session.title == "帮我整理一下本周的工作计划并写周报"[:20]


async def test_history_survives_multiple_turns(store):
    session = store.create()
    runtime = AgentRuntime(ScriptedLLM([final("第一轮"), final("第二轮"), final("第三轮")]), Settings(llm_mock=True))
    for text in ("第一句话", "第二句话", "第三句话"):
        await collect(runtime, session, text)

    assert len(session.visible_messages()) == 6
    assert visible_text(session).count("第") >= 3
