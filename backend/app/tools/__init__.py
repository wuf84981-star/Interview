"""导入本模块即完成全部工具注册（注册表是进程内单例）。"""

from app.tools import calculator, search, todo, weather  # noqa: F401  导入副作用即注册
from app.tools.registry import Tool, ToolRegistry, registry

__all__ = ["Tool", "ToolRegistry", "registry"]
