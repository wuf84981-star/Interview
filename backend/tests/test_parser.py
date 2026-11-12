"""解析器：模型输出千奇百怪，解析必须稳。"""

import json

from app.agent.parser import parse_llm_output


def test_pure_json_final():
    result = parse_llm_output('{"thought": "可以直接答", "final_answer": "你好"}')
    assert result.kind == "final"
    assert result.final_answer == "你好"
    assert result.thought == "可以直接答"


def test_pure_json_action():
    result = parse_llm_output(
        '{"thought": "查天气", "action": "weather", "action_input": {"city": "深圳"}}'
    )
    assert result.kind == "action"
    assert result.action == "weather"
    assert result.action_input == {"city": "深圳"}


def test_fenced_json_is_accepted():
    raw = '```json\n{"thought": "算一下", "action": "calculator", "action_input": {"expression": "1+1"}}\n```'
    result = parse_llm_output(raw)
    assert result.kind == "action"
    assert result.action == "calculator"


def test_noise_around_json():
    raw = '好的，我来处理：\n{"thought": "先算", "final_answer": "结果是 2"}\n希望有帮助。'
    result = parse_llm_output(raw)
    assert result.kind == "final"
    assert result.final_answer == "结果是 2"


def test_braces_inside_string_do_not_break_scanning():
    raw = '{"thought": "输出带 } 括号", "final_answer": "格式 {a: 1} 是对象"}'
    result = parse_llm_output(raw)
    assert result.kind == "final"
    assert result.final_answer == "格式 {a: 1} 是对象"


def test_invalid_output():
    result = parse_llm_output("我觉得应该查一下天气")
    assert result.kind == "invalid"
    assert result.error


def test_action_input_as_json_string():
    payload = {"thought": "查天气", "action": "weather", "action_input": '{"city": "北京"}'}
    result = parse_llm_output(json.dumps(payload))
    assert result.kind == "action"
    assert result.action_input == {"city": "北京"}


def test_missing_both_fields_is_invalid():
    result = parse_llm_output('{"thought": "我不知道该干嘛"}')
    assert result.kind == "invalid"
