"""应用装配：配置校验、CORS、路由、健康检查、生命周期收尾。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.runtime import AgentRuntime
from app.api import router
from app.common.logging import log_event, setup_logging
from app.config import Settings, load_settings
from app.llm.client import LLMClient
from app.llm.mock import RuleBasedLLM
from app.session.store import SessionStore
from app.tools.registry import registry


def build_llm(settings: Settings):
    """LLM_MOCK=1 时用规则模型，否则走真实 OpenAI 兼容接口。"""
    return RuleBasedLLM() if settings.llm_mock else LLMClient(settings)


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    settings = settings or load_settings()
    settings.validate()  # 缺配置就在启动时失败，不带病运行
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_event(
            "app_start",
            llm_mode="mock" if settings.llm_mock else "real",
            model=settings.llm_model or "-",
            tools=registry.names(),
        )
        yield
        client = getattr(app.state.runtime.llm, "aclose", None)
        if callable(client):
            await client()
        log_event("app_stop")

    app = FastAPI(title="MiniAgent API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.state.settings = settings
    app.state.store = SessionStore()
    app.state.runtime = AgentRuntime(llm or build_llm(settings), settings)

    app.include_router(router)

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "llm_mode": "mock" if settings.llm_mock else "real",
            "model": settings.llm_model or "-",
            "tools": registry.names(),
            "max_steps": settings.max_steps,
        }

    return app
