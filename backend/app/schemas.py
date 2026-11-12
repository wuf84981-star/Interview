"""请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, description="为空则新建会话")
    message: str = Field(min_length=1, max_length=4000, description="用户输入")

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message 不能为空")
        return stripped
