"""weather：内置模拟数据的城市天气查询（题目允许 mock）。"""

from __future__ import annotations

from app.common.errors import ToolError
from app.tools.registry import Tool, registry

WEATHER_DB: dict[str, dict] = {
    "深圳": {"condition": "多云", "temp": "26~31℃", "humidity": "68%", "wind": "东南风 2 级"},
    "北京": {"condition": "晴", "temp": "8~19℃", "humidity": "35%", "wind": "西北风 3 级"},
    "上海": {"condition": "小雨", "temp": "17~22℃", "humidity": "82%", "wind": "东风 2 级"},
    "广州": {"condition": "晴转多云", "temp": "24~30℃", "humidity": "70%", "wind": "南风 2 级"},
    "杭州": {"condition": "阴", "temp": "16~23℃", "humidity": "75%", "wind": "东北风 1 级"},
    "成都": {"condition": "多云转阴", "temp": "15~21℃", "humidity": "78%", "wind": "静风"},
}


def get_weather(session, args: dict) -> dict:
    raw_city = str(args["city"]).strip()
    city = raw_city.removesuffix("市").removesuffix("地区").strip() or raw_city
    data = WEATHER_DB.get(city)
    if data is None:
        raise ToolError(
            f"暂无 {raw_city} 的天气数据，可查询的城市：{'、'.join(WEATHER_DB)}"
        )
    return {"city": city, "date": "今天", **data}


registry.register(
    Tool(
        name="weather",
        description="查询指定城市今天的天气（内置模拟数据）。",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名，例如 深圳"},
            },
            "required": ["city"],
        },
        handler=get_weather,
    )
)
