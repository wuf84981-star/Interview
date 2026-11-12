"""工具注册表：Schema 声明与实际校验必须是同一份。"""

import pytest

from app.tools.registry import Tool, ToolRegistry


def echo(session, args):
    return {"echo": args}


@pytest.fixture
def reg() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="回显参数",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "count": {"type": "integer"},
                    "mode": {"type": "string", "enum": ["fast", "slow"]},
                },
                "required": ["text"],
            },
            handler=echo,
        )
    )
    return registry


def test_schema_exposed_to_llm(reg: ToolRegistry):
    schemas = reg.schemas()
    assert schemas[0]["name"] == "echo"
    assert "required" in schemas[0]["parameters"]


def test_invoke_success(reg: ToolRegistry, session):
    result = reg.invoke("echo", {"text": "hi"}, session)
    assert result["ok"] is True
    assert result["result"] == {"echo": {"text": "hi"}}
    assert result["elapsed_ms"] >= 0


def test_missing_required(reg: ToolRegistry, session):
    result = reg.invoke("echo", {}, session)
    assert result["ok"] is False
    assert "text" in result["result"]["error"]


def test_wrong_type(reg: ToolRegistry, session):
    result = reg.invoke("echo", {"text": "hi", "count": "3"}, session)
    assert result["ok"] is False
    assert "integer" in result["result"]["error"]


def test_enum_violation(reg: ToolRegistry, session):
    result = reg.invoke("echo", {"text": "hi", "mode": "turbo"}, session)
    assert result["ok"] is False


def test_unknown_tool(reg: ToolRegistry, session):
    result = reg.invoke("nope", {}, session)
    assert result["ok"] is False
    assert "未知工具" in result["result"]["error"]


def test_handler_exception_is_caught(reg: ToolRegistry, session):
    def boom(session, args):
        raise RuntimeError("内部炸了")

    reg.register(Tool(name="boom", description="故意异常", parameters={"type": "object", "properties": {}}, handler=boom))
    result = reg.invoke("boom", {}, session)
    assert result["ok"] is False
    assert "内部炸了" in result["result"]["error"]
