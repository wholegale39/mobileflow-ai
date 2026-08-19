"""Appium 封装层 —— WebDriver 动作适配器。

把 GLM-5.2 输出的 JSON 动作翻译成 Appium 调用：
- click / input / swipe / scroll / back / home / open_app / done
- 元素定位：text / resource_id / index 三种策略
- 设备不可用时支持 DryDriver（--dry-run 验证决策链路）
"""
from __future__ import annotations

from typing import Any

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver


class MobileDriver:
    """Appium WebDriver 封装。"""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def page_source(self) -> str:
        return self.driver.page_source

    def execute_action(self, action: dict[str, Any]) -> str:
        """执行一个动作 JSON，返回结果描述。"""
        act = action.get("action", "")
        target = action.get("target") or {}

        if act == "done":
            return f"✅ {action.get('summary', '任务完成')}"
        if act == "back":
            self.driver.back()
            return "↩️ 返回"
        if act == "home":
            self.driver.press_keycode(3)  # KEYCODE_HOME
            return "🏠 回桌面"
        if act == "open_app":
            pkg = target.get("package") or action.get("package") or target.get("text", "")
            self.driver.activate_app(pkg)
            return f"📱 打开应用 {pkg}"
        if act == "scroll":
            direction = action.get("direction", "down")
            return self._scroll(direction)
        if act == "swipe":
            start, end = action.get("start", [0, 0]), action.get("end", [0, 0])
            self.driver.swipe(start[0], start[1], end[0], end[1], 500)
            return f"👆 滑动 {start}→{end}"
        if act == "click":
            el = self._find_element(target)
            el.click()
            return f"👆 点击 {self._describe(target)}"
        if act == "input":
            el = self._find_element(target)
            text = action.get("text", "")
            el.clear()
            el.send_keys(text)
            return f"⌨️ 输入「{text}」到 {self._describe(target)}"
        raise ValueError(f"未知动作: {act}")

    # ---------- 内部 ----------

    def _find_element(self, target: dict[str, Any]):
        if target.get("text"):
            return self.driver.find_element(AppiumBy.XPATH, f'//*[@text="{target["text"]}"]')
        if target.get("resource_id"):
            return self.driver.find_element(AppiumBy.ID, target["resource_id"])
        if target.get("index") is not None:
            nodes = self.driver.find_elements(AppiumBy.XPATH, "//*[@clickable='true']")
            idx = int(target["index"])
            if idx >= len(nodes):
                raise ValueError(f"index {idx} 越界（可点元素共 {len(nodes)} 个）")
            return nodes[idx]
        raise ValueError(f"target 缺定位信息: {target}")

    @staticmethod
    def _describe(target: dict[str, Any]) -> str:
        if target.get("text"):
            return f"「{target['text']}」"
        if target.get("resource_id"):
            return target["resource_id"]
        return f"#{target.get('index')}"

    def _scroll(self, direction: str) -> str:
        size = self.driver.get_window_size()
        w, h = size["width"], size["height"]
        if direction == "down":
            self.driver.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), 400)
        else:
            self.driver.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.7), 400)
        return f"📜 滚动 {direction}"


class DryDriver:
    """无设备模式：只打印动作，用于验证 LLM 决策链路。"""

    def __init__(self, page_source_xml: str) -> None:
        self._xml = page_source_xml

    def page_source(self) -> str:
        return self._xml

    def execute_action(self, action: dict[str, Any]) -> str:
        return f"[dry-run] 执行: {action}"
