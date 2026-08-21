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
