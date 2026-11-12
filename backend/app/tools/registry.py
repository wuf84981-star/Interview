"""工具注册机制：名称 + 描述 + 参数 JSON Schema + 处理函数。

LLM 看到的就是 registry.schemas() 输出的 Schema，它据此自主决定调用哪个工具、
传什么参数；运行时再用同一份 Schema 校验参数，Schema 不是摆设。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from app.common.errors import ToolError
from app.common.logging import log_event

Handler = Callable[[object, dict], dict]

_TYPE_MAP: dict[str, tuple | type] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Handler

    def to_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ---------- 注册 ----------
    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册：{tool.name}")
        self._tools[tool.name] = tool
        return tool

    def tool(self, name: str, description: str, parameters: dict):
        """装饰器写法：@registry.tool(name=..., description=..., parameters=...)"""

        def decorator(func: Handler) -> Handler:
            self.register(Tool(name=name, description=description, parameters=parameters, handler=func))
            return func

        return decorator

    # ---------- 查询 ----------
    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"未知工具 {name!r}，可用工具：{', '.join(self.names())}")
        return tool

    def names(self) -> list[str]:
        return list(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    # ---------- 校验 ----------
    def validate(self, tool: Tool, args: dict) -> None:
        if not isinstance(args, dict):
            raise ToolError("action_input 必须是一个 JSON 对象")
        schema = tool.parameters or {}
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in args or args[key] in (None, ""):
                raise ToolError(f"参数错误：缺少必填参数 {key}")
        for key, value in args.items():
            spec = properties.get(key)
            if not spec:
                continue  # 未声明的额外参数放行，由 handler 自行判断
            expected = spec.get("type")
            if expected in _TYPE_MAP and not _type_ok(value, expected):
                raise ToolError(f"参数错误：{key} 应为 {expected}，实际为 {type(value).__name__}")
            choices = spec.get("enum")
            if choices and value not in choices:
                raise ToolError(f"参数错误：{key} 只能是 {choices} 之一，实际为 {value!r}")

    # ---------- 调度 ----------
    def invoke(self, name: str, args: dict, session: object) -> dict:
        start = time.perf_counter()
        tool_name = name
        try:
            tool = self.get(name)
            self.validate(tool, args)
            data = tool.handler(session, args)
            ok, payload = True, data
        except ToolError as exc:
            ok, payload = False, {"error": exc.message}
        except Exception as exc:  # 工具内部任何异常都不能打断循环
            log_event("tool_exception", tool=tool_name, error=repr(exc))
            ok, payload = False, {"error": f"工具执行失败：{exc}"}
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event("tool_result", tool=tool_name, ok=ok, elapsed_ms=elapsed_ms)
        return {"tool": tool_name, "ok": ok, "result": payload, "elapsed_ms": elapsed_ms}


def _type_ok(value: object, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPE_MAP[expected])


registry = ToolRegistry()
