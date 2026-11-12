"""集中读取并校验环境变量：配置只在这里出现，缺失即快速失败。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.common.errors import ConfigError

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 解析（不引入 python-dotenv）：KEY=VALUE，已存在的环境变量优先。"""
    path = path or BASE_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须是整数，当前为 {raw!r}") from exc


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: float = 30.0
    llm_mock: bool = False
    max_steps: int = 5
    context_char_budget: int = 6000
    keep_recent_messages: int = 8
    summary_max_chars: int = 600
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])

    def validate(self) -> None:
        """启动时集中校验：不允许带病运行。"""
        if self.max_steps < 1:
            raise ConfigError("MAX_STEPS 必须 >= 1")
        if self.keep_recent_messages < 2:
            raise ConfigError("KEEP_RECENT_MESSAGES 必须 >= 2")
        if self.context_char_budget < 500:
            raise ConfigError("CONTEXT_CHAR_BUDGET 必须 >= 500")
        if self.llm_mock:
            return
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", self.llm_base_url),
                ("LLM_API_KEY", self.llm_api_key),
                ("LLM_MODEL", self.llm_model),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "缺失必填环境变量：" + "、".join(missing) + "。"
                "请复制 backend/.env.example 为 backend/.env 并填写，"
                "或设置 LLM_MOCK=1 用内置 Mock 模型体验完整链路。"
            )


def load_settings() -> Settings:
    load_dotenv()
    origins = [
        item.strip()
        for item in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if item.strip()
    ]
    return Settings(
        llm_base_url=os.environ.get("LLM_BASE_URL", "").strip(),
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "").strip(),
        llm_timeout=float(os.environ.get("LLM_TIMEOUT", "30") or 30),
        llm_mock=_get_bool("LLM_MOCK"),
        max_steps=_get_int("MAX_STEPS", 5),
        context_char_budget=_get_int("CONTEXT_CHAR_BUDGET", 6000),
        keep_recent_messages=_get_int("KEEP_RECENT_MESSAGES", 8),
        summary_max_chars=_get_int("SUMMARY_MAX_CHARS", 600),
        cors_origins=origins or ["http://localhost:5173"],
    )
