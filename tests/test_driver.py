"""测试 driver 模块:动作执行、元素定位、新动作。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from mobileflow.driver import MobileDriver, DryDriver


class FakeAppiumDriver:
    """模拟 Appium WebDriver 用于单元测试。"""

    def __init__(self):
        self.calls = []
        self.window_size = {"width": 1080, "height": 1920}
        self._elements = {
            "微信": MagicMock(),
            "search": MagicMock(),
            "input": MagicMock(),
            "长按项": MagicMock(),
            "双击项": MagicMock(),
            "源": MagicMock(),
            "目标": MagicMock(),
            "搜索框": MagicMock(),
        }

    def find_element(self, by, value):
        self.calls.append(("find_element", by, value))
        for key, el in self._elements.items():
            if key in str(value):
                return el
        raise Exception(f"Element not found: {value}")

    def find_elements(self, by, value):
        self.calls.append(("find_elements", by, value))
        el = MagicMock()
        el.rect = {"x": 100, "y": 200, "width": 100, "height": 50}
        return [el] * 5

    def back(self):
        self.calls.append("back")
        return "back"

    def press_keycode(self, code):
        self.calls.append(("keycode", code))
        return f"keycode_{code}"

    def activate_app(self, pkg):
        self.calls.append(("activate_app", pkg))
        return f"opened_{pkg}"

    def swipe(self, sx, sy, ex, ey, duration):
        self.calls.append(("swipe", sx, sy, ex, ey, duration))
        return f"swipe_{sx}_{sy}_{ex}_{ey}"

    def tap(self, positions):
        self.calls.append(("tap", positions))
        return f"tap_{positions}"

    def drag_and_drop(self, origin_el, destination_el):
        self.calls.append(("drag", origin_el, destination_el))
        return "dragged"

    def get_screenshot_as_base64(self):
        return "iVBORw0KGgo="

    @property
    def page_source(self):
        return "<root><node text='微信'/></root>"

    def get_window_size(self):
        return self.window_size


def test_mobile_driver_init():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    assert driver.default_timeout == 10.0
    assert driver.default_retry == 3


def test_execute_done():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "done", "summary": "完成"})
    assert "✅" in result
    assert "完成" in result


def test_execute_back():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "back"})
    assert "↩️" in result
    assert len(fake.calls) == 1
    assert fake.calls[0] == "back"


def test_execute_home():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "home"})
    assert "🏠" in result
    assert ("keycode", 3) in fake.calls


def test_execute_open_app():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "open_app", "package": "com.example"})
    assert "📱" in result
    assert ("activate_app", "com.example") in fake.calls


def test_execute_scroll_down():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "scroll", "direction": "down"})
    assert "📜" in result
    swipe_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "swipe"]
    assert len(swipe_calls) == 1


def test_execute_swipe():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "swipe", "start": [540, 1000], "end": [540, 500]})
    assert "👆" in result
    swipe_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "swipe"]
    assert len(swipe_calls) == 1


def test_execute_click_by_text():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "click", "target": {"text": "微信"}})
    assert "👆" in result
    find_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "find_element"]
    assert any("微信" in str(c[2]) for c in find_calls)


def test_execute_click_by_resource_id():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "click", "target": {"resource_id": "com.example:id/search"}})
    assert "👆" in result


def test_execute_click_by_index():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "click", "target": {"index": 2}})
    assert "👆" in result


def test_execute_click_index_out_of_range():
    fake = FakeAppiumDriver()
    original = fake.find_elements
    fake.find_elements = lambda by, value: [MagicMock()]
    driver = MobileDriver(fake, default_retry=1)
    with pytest.raises(RuntimeError, match="动作执行失败"):
        driver.execute_action({"action": "click", "target": {"index": 5}})


def test_execute_long_click():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    result = driver.execute_action({"action": "long_click", "target": {"text": "长按项"}})
    assert "🖐️" in result
    swipe_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "swipe"]
    assert len(swipe_calls) >= 1


def test_execute_double_click():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    result = driver.execute_action({"action": "double_click", "target": {"text": "双击项"}})
    assert "👆👆" in result
    # double_click 应该执行两次 tap（或等效操作）


def test_execute_drag():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    result = driver.execute_action({
        "action": "drag",
        "from": {"text": "源"},
        "to": {"text": "目标"}
    })
    assert "↔️" in result
    assert ("drag",) in [c[:1] for c in fake.calls if isinstance(c, tuple)]


def test_execute_coordinate_click():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    result = driver.execute_action({"action": "coordinate_click", "x": 540, "y": 1000})
    assert "📍" in result
    tap_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "tap"]
    assert len(tap_calls) == 1
    assert (540, 1000) in tap_calls[0][1]


def test_execute_input_key():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    result = driver.execute_action({"action": "input_key", "keycode": 66})
    assert "⌨️" in result
    assert ("keycode", 66) in fake.calls


def test_execute_wait_present():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "wait", "target": {"text": "加载完成", "gone": False}})
    assert "⏳" in result
    assert "出现" in result


def test_execute_wait_gone():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    result = driver.execute_action({"action": "wait", "target": {"text": "广告", "gone": True}})
    assert "⏳" in result
    assert "消失" in result


def test_execute_unknown_action():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    with pytest.raises(RuntimeError, match="动作执行失败"):
        driver.execute_action({"action": "fly_to_moon"})


def test_execute_missing_target():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake, default_retry=1)
    with pytest.raises(RuntimeError, match="动作执行失败"):
        driver.execute_action({"action": "click"})


def test_screenshot_b64_success():
    fake = FakeAppiumDriver()
    driver = MobileDriver(fake)
    b64 = driver.screenshot_b64()
    assert b64 == "iVBORw0KGgo="


def test_screenshot_b64_failure():
    fake = FakeAppiumDriver()
    fake.get_screenshot_as_base64 = lambda: (_ for _ in ()).throw(Exception("截图失败"))
    driver = MobileDriver(fake)
    assert driver.screenshot_b64() is None


def test_describe_text():
    assert MobileDriver._describe({"text": "微信"}) == "「微信」"


def test_describe_resource_id():
    assert MobileDriver._describe({"resource_id": "com.example:id/wechat"}) == "com.example:id/wechat"


def test_describe_index():
    assert MobileDriver._describe({"index": 3}) == "#3"


class TestDryDriver:
    def test_page_source(self):
        driver = DryDriver("<root/>")
        assert driver.page_source() == "<root/>"

    def test_execute_action(self):
        driver = DryDriver("<root/>")
        result = driver.execute_action({"action": "click", "target": {"text": "test"}})
        assert "[dry-run]" in result
        assert "click" in result


def test_default_timeout_retry():
    driver = MobileDriver(FakeAppiumDriver(), default_timeout=15.0, default_retry=5)
    assert driver.default_timeout == 15.0
    assert driver.default_retry == 5
