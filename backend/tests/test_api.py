"""HTTP 接口：SSE 事件顺序、会话 CRUD、健康检查。"""

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.mock import ScriptedLLM
from app.main import create_app


def make_client(responses: list[str]) -> TestClient:
    app = create_app(settings=Settings(llm_mock=True), llm=ScriptedLLM(responses))
    return TestClient(app)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if name:
            events.append((name, data))
    return events


def final(answer: str) -> str:
    return json.dumps({"thought": "回答", "final_answer": answer}, ensure_ascii=False)


def action(name: str, **args) -> str:
    return json.dumps({"thought": "调工具", "action": name, "action_input": args}, ensure_ascii=False)


def test_health():
    client = make_client([])
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"
    assert set(body["tools"]) == {"calculator", "weather", "todo", "search"}


def test_chat_creates_session_and_streams_events():
    client = make_client([action("weather", city="深圳"), final("深圳多云")])
    response = client.post("/api/chat", json={"message": "深圳天气"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    assert [name for name, _ in events] == [
        "session",
        "step",
        "thought",
        "tool_call",
        "observation",
        "step",
        "thought",
        "answer",
    ]
    session_id = events[0][1]["session_id"]
    assert events[-1][1]["content"] == "深圳多云"

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["title"] == "深圳天气"
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["trace"][0]["tool"] == "weather"


def test_chat_continues_existing_session():
    client = make_client([final("第一次回答"), final("第二次回答")])
    first = parse_sse(client.post("/api/chat", json={"message": "第一句"}).text)
    session_id = first[0][1]["session_id"]

    second = parse_sse(
        client.post("/api/chat", json={"session_id": session_id, "message": "第二句"}).text
    )
    assert second[-1][1]["content"] == "第二次回答"

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert len(detail["messages"]) == 4


def test_chat_unknown_session_returns_404():
    client = make_client([final("不该被调用")])
    response = client.post("/api/chat", json={"session_id": "not-exist", "message": "你好"})
    assert response.status_code == 404


def test_empty_message_is_rejected():
    client = make_client([])
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422


def test_list_and_delete_sessions():
    client = make_client([final("好的")])
    session_id = parse_sse(client.post("/api/chat", json={"message": "建个会话"}).text)[0][1]["session_id"]

    listing = client.get("/api/sessions").json()["sessions"]
    assert any(item["id"] == session_id for item in listing)

    assert client.delete(f"/api/sessions/{session_id}").json() == {"ok": True}
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}").status_code == 404


def test_llm_failure_reports_error_event():
    client = make_client([])  # 脚本为空 → 模型调用失败
    events = parse_sse(client.post("/api/chat", json={"message": "你好"}).text)
    assert events[-1][0] == "error"
