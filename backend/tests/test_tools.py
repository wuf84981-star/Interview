"""四个真实工具的行为与边界。"""

import app.tools  # noqa: F401  注册工具
from app.tools.registry import registry


def call(name: str, args: dict, session):
    return registry.invoke(name, args, session)


# ---------------- calculator ----------------
def test_calculator_basic(session):
    result = call("calculator", {"expression": "(23*4+7)/5"}, session)
    assert result["ok"] is True
    assert result["result"]["result"] == 19.8
    assert result["result"]["expression"] == "(23*4+7)/5"


def test_calculator_integer_result_is_int(session):
    assert call("calculator", {"expression": "6/3"}, session)["result"]["result"] == 2


def test_calculator_divide_by_zero(session):
    result = call("calculator", {"expression": "1/0"}, session)
    assert result["ok"] is False
    assert "除数" in result["result"]["error"]


def test_calculator_rejects_code_injection(session):
    result = call("calculator", {"expression": "__import__('os').system('ls')"}, session)
    assert result["ok"] is False


def test_calculator_rejects_unknown_syntax(session):
    result = call("calculator", {"expression": "abc + 1"}, session)
    assert result["ok"] is False


# ---------------- weather ----------------
def test_weather_hit(session):
    result = call("weather", {"city": "深圳"}, session)
    assert result["ok"] is True
    assert result["result"]["city"] == "深圳"
    assert "condition" in result["result"]


def test_weather_accepts_city_suffix(session):
    assert call("weather", {"city": "北京市"}, session)["result"]["city"] == "北京"


def test_weather_miss_lists_cities(session):
    result = call("weather", {"city": "火星"}, session)
    assert result["ok"] is False
    assert "可查询的城市" in result["result"]["error"]


# ---------------- todo ----------------
def test_todo_add_and_list(session):
    added = call("todo", {"action": "add", "content": "买牛奶"}, session)
    assert added["ok"] is True
    assert added["result"]["todo"]["id"] == 1

    listed = call("todo", {"action": "list"}, session)
    assert listed["result"]["count"] == 1
    assert listed["result"]["todos"][0]["content"] == "买牛奶"


def test_todo_complete_and_delete(session):
    call("todo", {"action": "add", "content": "写周报"}, session)
    done = call("todo", {"action": "complete", "todo_id": 1}, session)
    assert done["result"]["todo"]["done"] is True

    deleted = call("todo", {"action": "delete", "todo_id": 1}, session)
    assert deleted["ok"] is True
    assert call("todo", {"action": "list"}, session)["result"]["count"] == 0


def test_todo_missing_content(session):
    result = call("todo", {"action": "add"}, session)
    assert result["ok"] is False


def test_todo_complete_unknown_id(session):
    result = call("todo", {"action": "complete", "todo_id": 99}, session)
    assert result["ok"] is False


def test_todo_is_isolated_per_session(store):
    first = store.create()
    second = store.create()
    call("todo", {"action": "add", "content": "A 的待办"}, first)

    assert call("todo", {"action": "list"}, first)["result"]["count"] == 1
    assert call("todo", {"action": "list"}, second)["result"]["count"] == 0


# ---------------- search ----------------
def test_search_hit(session):
    result = call("search", {"query": "年假几天"}, session)
    assert result["ok"] is True
    assert result["result"]["count"] > 0
    titles = " ".join(item["title"] for item in result["result"]["results"])
    assert "年假" in titles


def test_search_miss(session):
    result = call("search", {"query": "量子引力波"}, session)
    assert result["ok"] is True
    assert result["result"]["count"] == 0
