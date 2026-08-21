"""等待策略 —— 元素可见/消失等待 + 动作重试机制。

提供:
- wait_until(*args, timeout=10, interval=0.5): 等待条件函数变为 True
- wait_until_gone(text, resource_id=None, timeout=10): 等待元素消失
- retry_action(driver, action, max_attempts=3, delay=1.0): 带退避的动作重试
"""
from __future__ import annotations

import time
from typing import Any, Callable

from mobileflow.utils import escape_xpath_text


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 10.0,
    interval: float = 0.5,
    desc: str = "条件",
) -> bool:
    """轮询 condition() 直到返回 True 或超时。

    Returns:
        True 如果条件在 timeout 内变为 True,否则 False。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def wait_until_gone(
    driver: Any,
    text: str | None = None,
    resource_id: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """等待指定文本/resource_id 的元素消失。

    通过 AppiumBy 查找元素,找不到即视为消失。
    需要 driver 有 find_element/find_elements 方法(Appium WebDriver)。
    """
    if not text and not resource_id:
        raise ValueError("text 与 resource_id 至少需指定一个")
    from appium.webdriver.common.appiumby import AppiumBy

    def _gone() -> bool:
        try:
            if text:
                driver.find_element(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(text)}"]')
                return False
            if resource_id:
                driver.find_element(AppiumBy.ID, resource_id)
                return False
        except Exception:
            return True
        return False

    return wait_until(_gone, timeout=timeout, desc=f"元素 {text or resource_id} 消失")


def wait_until_present(
    driver: Any,
    text: str | None = None,
    resource_id: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """等待指定文本/resource_id 的元素出现。"""
    if not text and not resource_id:
        raise ValueError("text 与 resource_id 至少需指定一个")
    from appium.webdriver.common.appiumby import AppiumBy

    def _present() -> bool:
        try:
            if text:
                driver.find_element(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(text)}"]')
                return True
            if resource_id:
                driver.find_element(AppiumBy.ID, resource_id)
                return True
        except Exception:
            return False
        return False

    return wait_until(_present, timeout=timeout, desc=f"元素 {text or resource_id} 出现")


def retry_action(
    action_fn: Callable[[], str],
    *,
    max_attempts: int = 3,
    delay: float = 1.0,
    max_delay: float = 10.0,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> str:
    """带指数退避的重试包装。

    Args:
        action_fn: 执行动作的函数,返回结果描述。
        max_attempts: 最大重试次数。
        delay: 初始等待秒数(指数退避 base=2)。
        on_retry: 每次重试时的回调(on_retry(attempt, exc))。

    Returns:
        最后一次调用的结果描述。

    Raises:
        RuntimeError: 所有尝试都失败时抛出最后一次异常。
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return action_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = min(delay * (2 ** (attempt - 1)), max_delay)
                if on_retry:
                    on_retry(attempt, exc)
                print(f"  ⚠️ 第 {attempt} 次失败({exc}),{wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                print(f"  ❌ 已重试 {max_attempts} 次,全部失败: {exc}")
    raise RuntimeError(f"动作执行失败({max_attempts}次): {last_exc}") from last_exc
