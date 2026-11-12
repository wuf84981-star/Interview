"""OpenAI 兼容的 Chat Completions 客户端（只用 httpx，不用任何 agent SDK）。

重试策略：网络错误与 5xx 重试 1 次；4xx（Key 错、模型名错）直接失败，不重试。
"""

from __future__ import annotations

import asyncio

import httpx

from app.common.errors import LLMError
from app.common.logging import log_event
from app.config import Settings


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout)

    async def complete(self, messages: list[dict]) -> str:
        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        for attempt in (1, 2):
            try:
                response = await self._client.post(url, json=payload, headers=headers)
                if response.status_code >= 500:
                    last_error = f"上游返回 HTTP {response.status_code}"
                else:
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    if not isinstance(content, str) or not content.strip():
                        raise LLMError("模型返回了空内容，请重试")
                    return content
            except httpx.HTTPStatusError as exc:
                raise LLMError(
                    f"模型接口拒绝请求（HTTP {exc.response.status_code}），请检查 LLM_API_KEY 与 LLM_MODEL"
                ) from exc
            except LLMError:
                raise
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = str(exc) or exc.__class__.__name__

            log_event("llm_retry", attempt=attempt, error=last_error)
            if attempt == 1:
                await asyncio.sleep(0.5)

        raise LLMError("模型调用失败，请稍后重试")

    async def aclose(self) -> None:
        await self._client.aclose()
