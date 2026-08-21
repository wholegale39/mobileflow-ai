"""测试 wait_strategy 模块:等待条件、元素等待、动作重试。"""
from __future__ import annotations

import time

import pytest

from mobileflow.wait_strategy import (
    retry_action,
    wait_until,
    wait_until_gone,
    wait_until_present,
)


class FakeDriver:
    """模拟 Appium WebDriver 用于 wait_until_gone/present 测试。"""

    def __init__(self, present_text: str | None = None, present_id: str | None = None):
        self._present_text = present_text
        self._present_id = present_id
        self.find_count = 0

    def find_element(self, by, value):
        self.find_count += 1
        if value and self._present_text and self._present_text in str(value):
            return True
        if value and self._present_id and self._present_id in str(value):
            return True
        raise Exception("Element not found")

    def find_elements(self, by, value):
        return []


def test_wait_until_true_immediately():
    assert wait_until(lambda: True, timeout=1.0) is True


def test_wait_until_false_timeout():
    assert wait_until(lambda: False, timeout=0.2, interval=0.05) is False


def test_wait_until_true_after_delay():
    started = time.time()
    result = wait_until(lambda: time.time() - started > 0.15, timeout=1.0, interval=0.05)
    assert result is True
    assert time.time() - started >= 0.1


def test_wait_until_present_found():
    driver = FakeDriver(present_text="微信")
    assert wait_until_present(driver, text="微信", timeout=1.0) is True


def test_wait_until_present_not_found_timeout():
    driver = FakeDriver(present_text="支付宝")
    assert wait_until_present(driver, text="微信", timeout=0.2) is False


def test_wait_until_gone_found_then_gone():
    driver = FakeDriver(present_text="弹窗")
    # 第一次调用时元素存在,后续不存在
    call_count = [0]
    original_find = driver.find_element

    def counting_find(by, value):
        call_count[0] += 1
        if call_count[0] > 2:
            raise Exception("not found")
        return original_find(by, value)

    driver.find_element = counting_find
    # wait_until_gone 使用默认 interval=0.5,timeout 内可以检查多次
    assert wait_until_gone(driver, text="弹窗", timeout=5.0) is True


def test_retry_action_success_first_try():
    results = []
    def action():
        results.append(1)
        return "ok"
    assert retry_action(action, max_attempts=3) == "ok"
    assert len(results) == 1


def test_retry_action_success_after_failures():
    attempts = [0]
    def action():
        attempts[0] += 1
        if attempts[0] < 3:
            raise RuntimeError("fail")
        return "ok"
    result = retry_action(action, max_attempts=3, delay=0.01)
    assert result == "ok"
    assert attempts[0] == 3


def test_retry_action_all_fail():
    def action():
        raise RuntimeError("always fail")
    with pytest.raises(RuntimeError, match="动作执行失败"):
        retry_action(action, max_attempts=2, delay=0.01)


def test_retry_action_on_retry_callback():
    callbacks = []
    def action():
        raise RuntimeError("fail")
    def on_retry(n, exc):
        callbacks.append((n, str(exc)))
    with pytest.raises(RuntimeError):
        retry_action(action, max_attempts=2, delay=0.01, on_retry=on_retry)
    assert len(callbacks) == 1
    assert callbacks[0][0] == 1
