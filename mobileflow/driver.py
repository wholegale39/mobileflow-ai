"""Appium 封装层 —— WebDriver 动作适配器。

把 GLM-5.2 输出的 JSON 动作翻译成 Appium 调用：
- click / input / swipe / scroll / back / home / open_app / done
- long_click / double_click / drag / coordinate_click（新增）
- 元素定位：text / resource_id / index / coordinate 四种策略
- 等待策略集成（wait_until / retry_action）
- 设备不可用时支持 DryDriver（--dry-run 验证决策链路）
"""
from __future__ import annotations

import time
from typing import Any

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver

from mobileflow.wait_strategy import wait_until, retry_action
from mobileflow.utils import escape_xpath_text


class MobileDriver:
    """Appium WebDriver 封装。"""

    def __init__(
        self,
        driver: WebDriver,
        *,
        default_timeout: float = 10.0,
        default_retry: int = 3,
    ) -> None:
        self.driver = driver
        self.default_timeout = default_timeout
        self.default_retry = default_retry

    def page_source(self) -> str:
        return self.driver.page_source

    def screenshot_b64(self) -> str | None:
        """截图 base64（视觉通道用），失败返回 None。"""
        try:
            return self.driver.get_screenshot_as_base64()
        except Exception:
            return None

    def execute_action(self, action: dict[str, Any]) -> str:
        """执行一个动作 JSON，返回结果描述。支持重试。"""
        act = action.get("action", "")
        target = action.get("target") or {}
        timeout = action.get("timeout", self.default_timeout)

        def _exec() -> str:
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
            if act == "long_click":
                return self._long_click(target)
            if act == "double_click":
                return self._double_click(target)
            if act == "drag":
                start_el = self._find_element(action.get("from", {}))
                end_el = self._find_element(action.get("to", {}))
                self.driver.drag_and_drop(start_el, end_el)
                return f"↔️ 拖动 {self._describe(action.get('from', {}))} → {self._describe(action.get('to', {}))}"
            if act == "coordinate_click":
                x, y = action.get("x", 0), action.get("y", 0)
                self.driver.tap([(x, y)])
                return f"📍 点击坐标 ({x}, {y})"
            if act == "input":
                el = self._find_element(target)
                text = action.get("text", "")
                el.clear()
                el.send_keys(text)
                return f"⌨️ 输入「{text}」到 {self._describe(target)}"
            if act == "input_key":
                keycode = action.get("keycode", 66)  # 默认 Enter
                self.driver.press_keycode(int(keycode))
                keyname = {66: "Enter", 4: "Back", 3: "Home"}.get(keycode, str(keycode))
                return f"⌨️ 按键 {keyname}"
            if act == "wait":
                text = target.get("text")
                resource_id = target.get("resource_id")
                gone = target.get("gone", False)
                if gone:
                    ok = self._wait_gone(text, resource_id, timeout)
                    return f"⏳ 等待元素消失 {'✓' if ok else '✗'}"
                ok = self._wait_present(text, resource_id, timeout)
                return f"⏳ 等待元素出现 {'✓' if ok else '✗'}"
            raise ValueError(f"未知动作: {act}")

        # 仅对幂等/可恢复动作启用重试；input/drag/swipe/done 等非幂等或无状态动作不重试
        _NON_RETRYABLE = {"input", "drag", "swipe", "done"}
        max_attempts = 1 if act in _NON_RETRYABLE else action.get("retry", self.default_retry)
        return retry_action(_exec, max_attempts=max_attempts, on_retry=lambda n, e: print(f"  ⚠️ 重试 {n}: {e}"))

    # ---------- 长按/双击 ----------

    def _long_click(self, target: dict[str, Any]) -> str:
        """长按：用坐标 swipe 起点=终点 + duration 模拟长按（比 5px 偏移更可靠）。"""
        el = self._find_element(target)
        rect = el.rect
        cx, cy = rect["x"] + rect["width"] // 2, rect["y"] + rect["height"] // 2
        self.driver.swipe(cx, cy, cx, cy, 1000)
        return f"🖐️ 长按 {self._describe(target)}"

    def _double_click(self, target: dict[str, Any]) -> str:
        """双击：两次点击之间重新定位，避免 StaleElementReferenceException。"""
        el1 = self._find_element(target)
        el1.click()
        time.sleep(0.1)
        el2 = self._find_element(target)  # 重新定位，防止 stale
        el2.click()
        return f"👆👆 双击 {self._describe(target)}"

    # ---------- 内部 ----------

    def _find_element(self, target: dict[str, Any]):
        if target.get("text"):
            return self.driver.find_element(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(target["text"])}"]')
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

    def _wait_present(self, text: str | None, resource_id: str | None, timeout: float) -> bool:
        def _present() -> bool:
            try:
                if text:
                    self.driver.find_element(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(text)}"]')
                    return True
                if resource_id:
                    self.driver.find_element(AppiumBy.ID, resource_id)
                    return True
            except Exception:
                return False
            return False
        return wait_until(_present, timeout=timeout, desc=f"元素 {text or resource_id}")

    def _wait_gone(self, text: str | None, resource_id: str | None, timeout: float) -> bool:
        def _gone() -> bool:
            try:
                if text:
                    self.driver.find_element(AppiumBy.XPATH, f'//*[@text="{escape_xpath_text(text)}"]')
                    return False
                if resource_id:
                    self.driver.find_element(AppiumBy.ID, resource_id)
                    return False
            except Exception:
                return True
            return False
        return wait_until(_gone, timeout=timeout, desc=f"元素 {text or resource_id} 消失")


class DryDriver:
    """无设备模式：只打印动作，用于验证 LLM 决策链路。"""

    def __init__(self, page_source_xml: str) -> None:
        self._xml = page_source_xml

    def page_source(self) -> str:
        return self._xml

    def execute_action(self, action: dict[str, Any]) -> str:
        return f"[dry-run] 执行: {action}"
