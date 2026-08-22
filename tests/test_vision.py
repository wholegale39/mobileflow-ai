"""测试 vision 视觉通道：结构化元素解析。"""
from __future__ import annotations

from mobileflow.vision import VisionChannel


def test_parse_elements_valid():
    raw = '[{"name":"购买","x":540,"y":1200,"type":"button","note":"红色"}]'
    out = VisionChannel._parse_elements(raw)
    assert out[0]["name"] == "购买"
    assert out[0]["x"] == 540
    assert out[0]["type"] == "button"


def test_parse_elements_array():
    raw = '[{"name":"登录","x":100,"y":200,"type":"button"},' \
          '{"name":"输入框","x":300,"y":400,"type":"input"}]'
    out = VisionChannel._parse_elements(raw)
    assert len(out) == 2
    assert out[1]["name"] == "输入框"


def test_parse_elements_with_fencing():
    raw = '```json\n[{"name":"确定","x":0,"y":0,"type":"button"}]\n```'
    out = VisionChannel._parse_elements(raw)
    assert out[0]["name"] == "确定"


def test_parse_elements_malformed_returns_empty():
    assert VisionChannel._parse_elements("这不是json") == []
    assert VisionChannel._parse_elements("") == []
    assert VisionChannel._parse_elements("[]") == []


def test_parse_elements_skips_bad_items():
    # 坏项（x 非整数）被跳过，好项保留
    raw = '[{"name":"a","x":"bad","y":1,"type":"b"},' \
          '{"name":"b","x":10,"y":20,"type":"button"}]'
    out = VisionChannel._parse_elements(raw)
    assert len(out) == 1
    assert out[0]["name"] == "b"


# ---------- 视觉通道 key 回退 + describe/analyze 分支 ----------



def test_vision_api_key_from_own_env(monkeypatch):
    """未传 key 时应从 MOBILEFLOW_VISION_API_KEY 环境变量回退。"""
    monkeypatch.setenv("MOBILEFLOW_VISION_API_KEY", "sk-from-vision-env")
    v = VisionChannel()
    assert v.api_key == "sk-from-vision-env"


def test_vision_explicit_key_wins(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    v = VisionChannel(api_key="sk-explicit")
    assert v.api_key == "sk-explicit"


def test_describe_screenshot_calls_vision(monkeypatch):
    """describe_screenshot 应走 _call_vision 路径。"""
    v = VisionChannel(api_key="sk-x", base_url="https://x.test/v1")
    captured = {}

    def _fake_call(img, prompt):
        captured["img"] = img
        captured["prompt_has_describe"] = "要点" in prompt or "界面" in prompt
        return "要点1；要点2"
    monkeypatch.setattr(v, "_call_vision", _fake_call)
    out = v.describe_screenshot("imgdata")
    assert out == "要点1；要点2"
    assert captured["img"] == "imgdata"


def test_analyze_screenshot_calls_vision_and_parses(monkeypatch):
    v = VisionChannel(api_key="sk-x")
    monkeypatch.setattr(v, "_call_vision", lambda img, p:
        '[{"name":"登录","x":100,"y":200,"type":"button","note":"蓝"}]')
    out = v.analyze_screenshot("img")
    assert len(out) == 1
    assert out[0]["name"] == "登录"
    assert out[0]["x"] == 100
