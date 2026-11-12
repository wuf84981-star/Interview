"""结构化 JSON 日志：一行一条，统一携带 request_id。"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_LOGGER_NAME = "miniagent"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "request_id": request_id_var.get(),
            "event": record.getMessage(),
        }
        payload = getattr(record, "payload", None)
        if payload:
            data["payload"] = payload
        if record.exc_info:
            data["error"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(event: str, **payload) -> None:
    """记录一条结构化事件。不要放置密钥、密码等敏感字段。"""
    logging.getLogger(_LOGGER_NAME).info(event, extra={"payload": payload})
