from __future__ import annotations

import os
import sys

# 让 `tests/` 与 `mobileflow/` 同级时可直接 import mobileflow.skills
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from mobileflow.skills import SkillLibrary, _fill


def test_default_skills_listed():
    lib = SkillLibrary()
    keys = lib.list()
    assert "open_app" in keys
    assert "scroll_find" in keys


def test_match_open_app():
    lib = SkillLibrary()
    skill = lib.match("打开微信")
    assert skill is not None
    assert skill["name"] == "打开应用"


def test_match_none_for_unrelated():
    lib = SkillLibrary()
    skill = lib.match("asdfqwxyz unrelated junk")
    assert skill is None


def test_render_steps_replaces_param():
    lib = SkillLibrary()
    open_app_skill = lib.skills["open_app"]
    steps = lib.render_steps(open_app_skill, {"app": "微信"})
    assert any(step.get("package") == "微信" for step in steps)


def test_render_steps_replaces_nested():
    lib = SkillLibrary()
    scroll_skill = lib.skills["scroll_find"]
    steps = lib.render_steps(scroll_skill, {"target": "登录"})
    found = False
    for step in steps:
        target = step.get("target")
        if isinstance(target, dict) and target.get("text") == "登录":
            found = True
            break
    assert found


def test_add_and_reload(tmp_path):
    lib = SkillLibrary(str(tmp_path))
    custom = {
        "name": "自定义技能",
        "description": "用于测试的自定义技能",
        "params": {"target": "示例"},
        "steps": [
            {"action": "click", "target": {"text": "{target}"}},
        ],
    }
    lib.add(custom)
    assert "自定义技能" in lib.list()

    new_lib = SkillLibrary(str(tmp_path))
    assert "自定义技能" in new_lib.list()

    loaded = new_lib.skills["自定义技能"]
    assert loaded["name"] == custom["name"]
    assert loaded["description"] == custom["description"]
    assert loaded["params"] == custom["params"]
    assert loaded["steps"] == custom["steps"]


def test_fill_returns_non_str_list_dict_unchanged():
    result_int = _fill(42, "{x}", "v")
    assert result_int == 42
    assert id(result_int) == id(42)

    result_none = _fill(None, "{x}", "v")
    assert result_none is None

    result_bool = _fill(True, "{x}", "v")
    assert result_bool is True
    assert id(result_bool) == id(True)
