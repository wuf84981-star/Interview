"""上下文组装与压缩。"""

from app.agent.context import build_context, maybe_compress
from app.agent.prompt import render_system_prompt
from app.config import Settings
from app.session.store import Message

SYSTEM = render_system_prompt([], 5)


def user(text: str) -> Message:
    return Message(role="user", content=text, text=text)


def assistant_final(text: str) -> Message:
    return Message(
        role="assistant",
        content='{"thought": "t", "final_answer": "%s"}' % text,
        text=text,
    )


def tool_result(name: str, payload: str) -> Message:
    return Message(role="tool", content=payload, tool_name=name, visible=False)


def test_context_order_and_rendering(session):
    session.add(user("查一下深圳天气"))
    session.add(Message(role="assistant", content='{"action": "weather"}', thought="查天气", tool_name="weather", visible=False))
    session.add(tool_result("weather", '{"city": "深圳", "condition": "多云"}'))
    session.add(assistant_final("深圳多云"))

    context = build_context(session, SYSTEM)

    assert context[0]["role"] == "system"
    assert context[1] == {"role": "user", "content": "查一下深圳天气"}
    assert context[2]["role"] == "assistant"
    assert context[3]["content"].startswith("Observation(weather):")
    assert context[4]["content"] == '{"thought": "t", "final_answer": "深圳多云"}'


def test_summary_is_injected_as_system_message(session):
    session.summary = "用户: 之前问过北京天气\n助手: 北京晴"
    session.add(user("那上海呢"))

    context = build_context(session, SYSTEM)
    assert context[1]["role"] == "system"
    assert "北京天气" in context[1]["content"]


def test_no_compression_below_budget(session):
    for index in range(5):
        session.add(user(f"第 {index} 条消息"))
    assert maybe_compress(session, Settings(llm_mock=True)) == 0
    assert session.compressed_upto == 0


def test_compression_triggers_and_keeps_recent(session):
    settings = Settings(llm_mock=True, context_char_budget=200, keep_recent_messages=3)
    for index in range(10):
        session.add(user(f"第 {index} 条比较长的用户消息" + "内" * 20))

    dropped = maybe_compress(session, settings)

    assert dropped == 7
    assert session.compressed_upto == 7
    assert "第 0 条" in session.summary
    assert "第 9 条" not in session.summary  # 最近的 3 条保持原样

    context = build_context(session, settings and SYSTEM)
    assert len(context) == 1 + 1 + 3  # system + summary + 保留的消息


def test_compression_skips_invisible_assistant_steps(session):
    settings = Settings(llm_mock=True, context_char_budget=50, keep_recent_messages=2)
    session.add(user("问题一"))
    session.add(Message(role="assistant", content="原始 JSON 很长的中间步骤", visible=False))
    session.add(tool_result("weather", '{"city": "深圳"}'))
    session.add(user("问题二" + "长" * 100))
    session.add(user("问题三"))

    maybe_compress(session, settings)

    assert "原始 JSON" not in session.summary
    assert "工具 weather" in session.summary
    assert session.compressed_upto == 3


def test_summary_is_truncated(session):
    settings = Settings(llm_mock=True, context_char_budget=10, keep_recent_messages=2, summary_max_chars=80)
    for index in range(12):
        session.add(user(f"用户第 {index} 条消息" + "长" * 30))

    maybe_compress(session, settings)

    assert len(session.summary) <= 80
    assert session.compressed_upto == 10
