"""HTTP 接口：会话 CRUD + SSE 对话流。"""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent.runtime import AgentRuntime
from app.common.logging import log_event, request_id_var
from app.schemas import ChatRequest
from app.session.store import SessionStore


def assign_request_id() -> None:
    """给非流式接口分配 request_id，贯穿该请求的所有日志。"""
    request_id_var.set(uuid4().hex[:8])


router = APIRouter(prefix="/api", dependencies=[Depends(assign_request_id)])


def _store(request: Request) -> SessionStore:
    return request.app.state.store


def _runtime(request: Request) -> AgentRuntime:
    return request.app.state.runtime


def _sse(event: dict) -> str:
    payload = json.dumps(event["data"], ensure_ascii=False)
    return f"event: {event['event']}\ndata: {payload}\n\n"


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    store = _store(request)
    runtime = _runtime(request)

    if payload.session_id:
        session = store.get(payload.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if session.lock.locked():
            raise HTTPException(status_code=409, detail="该会话正在处理中，请稍后再试")
    else:
        session = store.create()

    request_id = uuid4().hex[:8]

    async def event_stream():
        # 流式响应在中间件之后才执行，这里显式绑定 request_id
        request_id_var.set(request_id)
        async with session.lock:
            try:
                async for event in runtime.run_turn(session, payload.message):
                    yield _sse(event)
            except Exception as exc:  # 兜底：任何未预期异常都不能让连接悬挂
                log_event("stream_error", session_id=session.id, error=repr(exc))
                yield _sse({"event": "error", "data": {"message": "服务内部错误，请稍后重试"}})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    return {"sessions": _store(request).list()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    session = _store(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.to_detail_dict()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    if not _store(request).delete(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}
