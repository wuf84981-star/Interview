"""todo：待办管理。数据挂在 session.state 上，因此不同窗口互不影响。"""

from __future__ import annotations

from app.common.errors import ToolError
from app.tools.registry import Tool, registry

ACTIONS = ["add", "list", "complete", "delete"]


def _find(todos: list[dict], todo_id: int) -> dict:
    for item in todos:
        if item["id"] == todo_id:
            return item
    raise ToolError(f"未找到 id 为 {todo_id} 的待办")


def manage_todo(session, args: dict) -> dict:
    action = args["action"]
    todos = session.todos  # type: ignore[attr-defined]

    if action == "add":
        content = str(args.get("content", "")).strip()
        if not content:
            raise ToolError("add 操作必须提供 content")
        next_id = max((item["id"] for item in todos), default=0) + 1
        item = {"id": next_id, "content": content, "done": False}
        todos.append(item)
        return {"action": "add", "todo": item, "todos": todos}

    if action == "list":
        return {"action": "list", "todos": todos, "count": len(todos)}

    todo_id = args.get("todo_id")
    if todo_id is None:
        raise ToolError(f"{action} 操作必须提供 todo_id")

    if action == "complete":
        item = _find(todos, todo_id)
        item["done"] = True
        return {"action": "complete", "todo": item, "todos": todos}

    if action == "delete":
        item = _find(todos, todo_id)
        todos.remove(item)
        return {"action": "delete", "todo": item, "todos": todos}

    raise ToolError(f"未知 action：{action}")


registry.register(
    Tool(
        name="todo",
        description="管理当前会话的待办事项：add 新增、list 查看、complete 标记完成、delete 删除。",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ACTIONS,
                    "description": "操作类型",
                },
                "content": {"type": "string", "description": "待办内容，add 时必填"},
                "todo_id": {"type": "integer", "description": "待办 id，complete/delete 时必填"},
            },
            "required": ["action"],
        },
        handler=manage_todo,
    )
)
