"""测试 usecase LLM 用例生成：生成/校验/保存。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mobileflow.usecase import (
    _VALID_ACTIONS,
    _parse,
    generate,
    generate_and_save,
    sanitize_filename,
    save,
    validate,
)


def test_validate_ok():
    skill = {"name": "登录", "description": "d", "params": {"user": "u"},
             "steps": [{"action": "input", "target": {"text": "u"}, "text": "{user}"}, {"action": "assert_text_exists", "text": "欢迎"}]}
    assert validate(skill)["ok"] is True


def test_validate_invalid_action():
    skill = {"name": "x", "params": {}, "steps": [{"action": "fly"}]}
    r = validate(skill)
    assert r["ok"] is False
    assert any("非法动作" in e for e in r["errors"])


def test_validate_undeclared_param():
    skill = {"name": "x", "params": {}, "steps": [{"action": "input", "target": {"text": "u"}, "text": "{pwd}"}]}
    r = validate(skill)
    assert r["ok"] is False
    assert any("未声明" in e for e in r["errors"])


def test_validate_click_missing_target():
    skill = {"name": "x", "params": {}, "steps": [{"action": "click"}]}
    r = validate(skill)
    assert r["ok"] is False
    assert any("缺 target" in e for e in r["errors"])


def test_validate_missing_steps():
    r = validate({"name": "x", "params": {}, "steps": []})
    assert r["ok"] is False
    assert any("非空" in e for e in r["errors"])


def test_parse_json_plain():
    obj = _parse('{"name":"a","steps":[]}')
    assert obj == {"name": "a", "steps": []}


def test_parse_json_in_codeblock():
    obj = _parse('```json\n{"name":"b","steps":[]}\n```')
    assert obj == {"name": "b", "steps": []}


def test_parse_invalid_none():
    assert _parse("这不是 json") is None


def test_parse_multi_codeblock_picks_first():
    # 第一个代码块即有效 dict 时返回第一个; 尾部注释不影响
    raw = "```json\n{\"name\":\"first\",\"steps\":[]}\n```\n```json\n{\"name\":\"second\"}\n```\n尾部"
    obj = _parse(raw)
    assert obj == {"name": "first", "steps": []}


def test_sanitize_filename_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("冒烟/测试") == "冒烟_测试"
    assert sanitize_filename("") == "case"


def test_generate_uses_llm_and_parses():
    llm = MagicMock()
    llm.chat_raw.return_value = '{"name":"注册","params":{"p":"pwd"},"steps":[{"action":"input","target":{"text":"密码"},"text":"{p}"},{"action":"done"}]}'
    skill = generate("用户注册场景", llm, app="测试App")
    assert skill["name"] == "注册"
    assert "注册" in llm.chat_raw.call_args[0][0]
    assert validate(skill)["ok"] is True


def test_generate_empty_llm_raises():
    llm = MagicMock()
    llm.chat_raw.return_value = ""
    with pytest.raises(ValueError, match="返回空"):
        generate("x", llm)


def test_generate_invalid_json_raises():
    llm = MagicMock()
    llm.chat_raw.return_value = "随便说点什么"
    with pytest.raises(ValueError, match="未能解析"):
        generate("x", llm)


def test_save_writes_yaml(tmp_path):
    skill = {"name": "登录用例", "description": "d", "params": {},
             "steps": [{"action": "click", "target": {"text": "登录"}}]}
    p = save(skill, tmp_path / "case.yaml")
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["name"] == "登录用例"
    assert data["steps"][0]["action"] == "click"


def test_save_invalid_raises():
    with pytest.raises(ValueError, match="校验未通过"):
        save({"name": "x", "params": {}, "steps": [{"action": "fly"}]}, "/tmp/x.yaml")


def test_generate_and_save_end_to_end(tmp_path):
    llm = MagicMock()
    llm.chat_raw.return_value = '{"name":"冒烟","params":{},"steps":[{"action":"done"}]}'
    p = generate_and_save("基本冒烟测试", llm, out_dir=tmp_path / "cases")
    assert p.exists() and p.suffix == ".yaml"


def test_valid_actions_nonempty():
    assert "click" in _VALID_ACTIONS
    assert "assert_text_exists" in _VALID_ACTIONS
