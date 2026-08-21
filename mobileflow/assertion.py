"""断言增强 —— 元素 / 视觉 / 性能·网络 三类断言。

用例里可内嵌断言动作，执行时校验并失败即抛 AssertionError（含诊断信息）：
- {"action": "assert_text_exists", "text": "提交成功"} 元素文本存在
- {"action": "assert_text_gone", "text": "加载中"} 元素消失
- {"action": "assert_text_contains", "text": "订单", "contains": "已完成"}
- {"action": "assert_visible", "name": "购买按钮"} 视觉模型确认屏幕上可见
- {"action": "assert_memory", "max_mb": 300} 应用内存不超阈值
- {"action": "assert_network", "online": true} 网络可达性

非幂等？否——断言只读不改变 UI，因此可安全重试。
"""
from __future__ import annotations

import re
from typing import Any

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver

from mobileflow.utils import escape_xpath_text
from mobileflow.vision import VisionChannel


class AssertionFailed(RuntimeError):
    """断言失败。"""


def run_assert(driver: WebDriver, action: dict[str, Any], *, vision: VisionChannel | None = None) -> str:
    """执行一个断言动作，通过返回描述，失败抛 AssertionFailed。"""
    kind = action.get("action")
    if kind == "assert_text_exists":
        return _assert_text_exists(driver, action)
    if kind == "assert_text_gone":
        return _assert_text_gone(driver, action)
    if kind == "assert_text_contains":
        return _assert_text_contains(driver, action)
    if kind == "assert_visible":
        if not vision:
            raise RuntimeError("assert_visible 需要 MobileDriver(vision=...) 配置视觉通道")
        return _assert_visible(driver, action, vision)
    if kind == "assert_memory":
        return _assert_memory(driver, action)
    if kind == "assert_network":
        return _assert_network(driver, action)
    raise ValueError(f"未知断言: {kind}")


# ---------- 元素断言 ----------

def _find_by_text(driver: WebDriver, text: str):
    return driver.find_elements(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(text)}"]')


def _assert_text_exists(driver: WebDriver, action: dict[str, Any]) -> str:
    text = action.get("text", "")
    if not text:
        raise AssertionFailed("assert_text_exists 缺 text")
    found = _find_by_text(driver, text)
    if not found:
        raise AssertionFailed(f"断言失败: 屏幕不存在文本「{text}」")
    return f"✓ 断言通过: 存在文本「{text}」"


def _assert_text_gone(driver: WebDriver, action: dict[str, Any]) -> str:
    text = action.get("text", "")
    if not text:
        raise AssertionFailed("assert_text_gone 缺 text")
    found = _find_by_text(driver, text)
    if found:
        raise AssertionFailed(f"断言失败: 文本「{text}」仍存在于屏幕")
    return f"✓ 断言通过: 文本「{text}」已消失"


def _assert_text_contains(driver: WebDriver, action: dict[str, Any]) -> str:
    text = action.get("text", "")
    contains = action.get("contains", "")
    if not text or not contains:
        raise AssertionFailed("assert_text_contains 需 text 和 contains")
    found = _find_by_text(driver, text)
    if not found:
        raise AssertionFailed(f"断言失败: 未找到文本「{text}」")
    matched = [el for el in found if contains in (el.text or "")]
    if not matched:
        samples = [el.text for el in found[:3]]
        raise AssertionFailed(f"断言失败: 文本「{text}」存在但内容不含「{contains}」(样本: {samples})")
    return f"✓ 断言通过: 「{text}」包含「{contains}」"


def _name_match(target: str, element: str) -> bool:
    """元素名匹配: 全等, 或 target 作为 element 中以中文标点/空格隔开的完整片段。

    避免短串误命中（"买" 不命中 "购买按钮"），但允许 "购买按钮" 命中 "按钮(购买)" 这类含括注。
    """
    if target == element:
        return True
    # 把 element 按中文标点/括号/空格切分成片段, target 需等于某片段
    segs = re.split(r"[，。、；：,;:\s()（）\[\]【】]+", element)
    return target in segs

# ---------- 视觉断言 ----------

def _assert_visible(driver: WebDriver, action: dict[str, Any], vision: VisionChannel) -> str:
    """截屏→视觉模型识别元素列表，确认目标在屏幕上。"""
    name = action.get("name", "")
    if not name:
        raise AssertionFailed("assert_visible 缺 name")
    b64 = None
    try:
        b64 = driver.get_screenshot_as_base64()
    except Exception:  # noqa: BLE001 (# intentional broad: 设备采集异常统一转为 AssertionFailed)
        raise AssertionFailed("断言失败: 截屏失败")
    if not b64:
        raise AssertionFailed("断言失败: 截屏为空")
    try:
        elements = vision.analyze_screenshot(b64)
    except Exception as e:  # noqa: BLE001 (# intentional broad: 设备采集异常统一转为 AssertionFailed)
        raise AssertionFailed(f"断言失败: 视觉分析异常 ({e})")
    n = str(name).strip()
    for el in elements:
        en = str(el.get("name", "")).strip()
        # 严格匹配: 全等 或 用中文停顿/边界隔开的整体词匹配，避免"买"误命中"购买按钮"
        if _name_match(n, en):
            return f"✓ 视觉断言通过: 屏幕可见「{name}」({el.get('x')},{el.get('y')})"
    raise AssertionFailed(
        f"视觉断言失败: 屏幕未识别到「{name}」"
        f"(已识别: {[e.get('name') for e in elements]})"
    )


# ---------- 性能 / 网络 ----------

def _assert_memory(driver: WebDriver, action: dict[str, Any]) -> str:
    max_mb = action.get("max_mb")
    if max_mb is None:
        raise AssertionFailed("assert_memory 缺 max_mb")
    try:
        pkg = action.get("package") or _default_package(driver)
        driver.get_performance_data_types()
        data = driver.get_performance_data(pkg, "android.memory", 1000)
        # get_performance_data 返回 list[str]，每个元素一行 JSON
        raw = data[0] if isinstance(data, list) and data else data
        if raw is None:
            raise AssertionFailed("断言失败: 性能数据为空(设备可能不支持性能数据采集)")
        raw = str(raw)
        # data 形如 '{"ss":"...","memUsed":...,"cpuUsed":...}'
        import json as _json
        used = _json.loads(raw)["memUsed"]  # KB
        used_mb = used / 1024
    except Exception as e:  # noqa: BLE001 (# intentional broad: 设备采集异常统一转为 AssertionFailed)
        raise AssertionFailed(f"断言失败: 获取内存数据异常 ({e}); 注意模拟器/部分设备不支持性能数据")
    if used_mb > max_mb:
        raise AssertionFailed(f"断言失败: 应用内存 {used_mb:.0f}MB 超过阈值 {max_mb}MB")
    return f"✓ 断言通过: 内存 {used_mb:.0f}MB ≤ {max_mb}MB"


def _assert_network(driver: WebDriver, action: dict[str, Any]) -> str:
    online = action.get("online")
    if online is None:
        raise AssertionFailed("assert_network 缺 online (true/false)")
    try:
        conn = driver.network_connection
        # network_connection 可能是 int 位掩码(航空1/手机2/WiFi4)或对象
        if isinstance(conn, int):
            is_online = bool(conn & 6)  # 手机或WiFi任意一位
        else:
            is_online = bool(getattr(conn, "wifi", 0) or getattr(conn, "mobile_data", 0))
    except Exception as e:  # noqa: BLE001 (# intentional broad: 设备采集异常统一转为 AssertionFailed)
        raise AssertionFailed(f"断言失败: 获取网络状态异常 ({e})")
    if bool(online) != is_online:
        raise AssertionFailed(f"断言失败: 期望网络{'可达' if online else '断开'}，实际{'在线' if is_online else '离线'}")
    return f"✓ 断言通过: 网络{'可达' if online else '断开'}"


def _default_package(driver: WebDriver) -> str:
    try:
        return driver.current_package or ""
    except Exception:  # noqa: BLE001 (# intentional broad: 设备采集异常统一转为 AssertionFailed)
        return ""
