"""类型化异常：对外只暴露可读消息，绝不泄露堆栈与内部细节。"""


class AppError(Exception):
    """应用异常基类。"""

    code = "app_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigError(AppError):
    """环境变量缺失或非法，启动即失败。"""

    code = "config_error"


class LLMError(AppError):
    """模型调用失败（超时、5xx、响应结构异常）。"""

    code = "llm_error"


class ToolError(AppError):
    """工具不存在、参数不合法或执行失败。"""

    code = "tool_error"


class ParseError(AppError):
    """模型输出无法解析为协议格式。"""

    code = "parse_error"
