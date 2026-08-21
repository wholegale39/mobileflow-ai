"""测试 assertion 断言增强：元素/视觉/性能/网络。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mobileflow.assertion import AssertionFailed, run_assert
AssertionError = AssertionFailed


# ---------- 元素断言 ----------

class FakeEl:
    def __init__(self, text=""):
        self.text = text


def _driver(elements=None):
    d = MagicMock()
    d.find_elements.return_value = elements or []
    return d


def test_assert_text_exists_pass():
    d = _driver([FakeEl("提交成功")])
    assert "通过" in run_assert(d, {"action": "assert_text_exists", "text": "提交成功"})


def test_assert_text_exists_fail():
    # find_elements 找不到匹配元素时返回空列表
    d = _driver([])
    with pytest.raises(AssertionFailed, match="不存在文本"):
        run_assert(d, {"action": "assert_text_exists", "text": "提交成功"})


def test_assert_text_gone():
    d = _driver([])
    assert "通过" in run_assert(d, {"action": "assert_text_gone", "text": "加载中"})
    d2 = _driver([FakeEl("加载中")])
    with pytest.raises(AssertionFailed, match="仍存在"):
        run_assert(d2, {"action": "assert_text_gone", "text": "加载中"})


def test_assert_text_contains():
    d = _driver([FakeEl("订单已完成"), FakeEl("订单")])
    assert "通过" in run_assert(d, {"action": "assert_text_contains", "text": "订单", "contains": "已完成"})
    d2 = _driver([FakeEl("订单待处理")])
    with pytest.raises(AssertionFailed, match="不含"):
        run_assert(d2, {"action": "assert_text_contains", "text": "订单", "contains": "已完成"})


# ---------- 视觉断言 ----------

def test_assert_visible_pass():
    d = _driver()
    d.get_screenshot_as_base64.return_value = "img"
    vision = MagicMock()
    vision.analyze_screenshot.return_value = [{"name": "购买", "x": 540, "y": 1200}]
    assert "购买" in run_assert(d, {"action": "assert_visible", "name": "购买"}, vision=vision)


def test_assert_visible_fail():
    d = _driver()
    d.get_screenshot_as_base64.return_value = "img"
    vision = MagicMock()
    vision.analyze_screenshot.return_value = [{"name": "返回", "x": 50, "y": 50}]
    with pytest.raises(AssertionFailed, match="未识别到"):
        run_assert(d, {"action": "assert_visible", "name": "购买"}, vision=vision)


# ---------- 性能/网络 ----------

def test_assert_memory_pass():
    d = MagicMock()
    d.get_performance_data.return_value = ['{"memUsed": 200000}']
    assert "通过" in run_assert(d, {"action": "assert_memory", "max_mb": 300})


def test_assert_memory_fail():
    d = MagicMock()
    d.get_performance_data.return_value = ['{"memUsed": 400000}']
    with pytest.raises(AssertionFailed, match="超过阈值"):
        run_assert(d, {"action": "assert_memory", "max_mb": 300})


def test_assert_network_int_mask():
    d = MagicMock()
    d.network_connection = 4  # WiFi 位
    assert "通过" in run_assert(d, {"action": "assert_network", "online": True})
    d.network_connection = 1  # 仅航空模式（离线）
    with pytest.raises(AssertionFailed, match="离线"):
        run_assert(d, {"action": "assert_network", "online": True})


def test_assert_unknown_action():
    with pytest.raises(ValueError, match="未知断言"):
        run_assert(_driver(), {"action": "assert_foo"})
