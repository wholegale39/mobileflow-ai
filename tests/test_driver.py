"""
tests/test_driver.py - MobileDriver 与 DryDriver 的 pytest 测试。
"""

from unittest.mock import MagicMock

import pytest

from mobileflow.driver import DryDriver, MobileDriver


class TestDriver:
    """组织 MobileDriver / DryDriver 相关测试。"""

    # ------------------------------------------------------------------ #
    # click
    # ------------------------------------------------------------------ #
    def test_click_by_text(self):
        driver = MagicMock()
        target = {"text": "登录"}
        action = {"action": "click", "target": target}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.find_element.assert_called_once_with("xpath", '//*[@text="登录"]')
        el = driver.find_element.return_value
        el.click.assert_called_once()
        assert result == "👆 点击 「登录」"

    def test_click_by_resource_id(self):
        driver = MagicMock()
        target = {"resource_id": "com.app:id/login_btn"}
        action = {"action": "click", "target": target}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.find_element.assert_called_once_with(
            "id", "com.app:id/login_btn"
        )
        el = driver.find_element.return_value
        el.click.assert_called_once()
        assert result == "👆 点击 com.app:id/login_btn"

    def test_click_by_index(self):
        driver = MagicMock()
        nodes = [MagicMock(name=f"node{i}") for i in range(3)]
        driver.find_elements.return_value = nodes
        target = {"index": 1}
        action = {"action": "click", "target": target}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.find_elements.assert_called_once_with(
            "xpath", "//*[@clickable='true']"
        )
        nodes[1].click.assert_called_once()
        assert result == "👆 点击 #1"

    def test_click_index_out_of_range(self):
        driver = MagicMock()
        driver.find_elements.return_value = [MagicMock() for _ in range(2)]
        target = {"index": 5}
        action = {"action": "click", "target": target}

        md = MobileDriver(driver)
        with pytest.raises(ValueError, match=r"index 5 越界"):
            md.execute_action(action)

    # ------------------------------------------------------------------ #
    # input
    # ------------------------------------------------------------------ #
    def test_input_clear_then_send_keys(self):
        driver = MagicMock()
        el = MagicMock()
        driver.find_element.return_value = el
        target = {"text": "搜索框"}
        action = {"action": "input", "target": target, "text": "hello"}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.find_element.assert_called_once_with("xpath", '//*[@text="搜索框"]')
        el.clear.assert_called_once()
        el.send_keys.assert_called_once_with("hello")
        assert "hello" in result
        assert result == "⌨️ 输入「hello」到 「搜索框」"

    def test_input_default_text_empty(self):
        driver = MagicMock()
        el = MagicMock()
        driver.find_element.return_value = el
        target = {"resource_id": "com.app:id/search"}
        action = {"action": "input", "target": target}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        el.clear.assert_called_once()
        el.send_keys.assert_called_once_with("")
        assert result == "⌨️ 输入「」到 com.app:id/search"

    # ------------------------------------------------------------------ #
    # swipe
    # ------------------------------------------------------------------ #
    def test_swipe_with_start_end(self):
        driver = MagicMock()
        action = {
            "action": "swipe",
            "start": [100, 200],
            "end": [300, 400],
        }

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.swipe.assert_called_once_with(100, 200, 300, 400, 500)
        assert result == "👆 滑动 [100, 200]→[300, 400]"

    def test_swipe_default_start_end(self):
        driver = MagicMock()
        action = {"action": "swipe"}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.swipe.assert_called_once_with(0, 0, 0, 0, 500)
        assert result == "👆 滑动 [0, 0]→[0, 0]"

    # ------------------------------------------------------------------ #
    # scroll
    # ------------------------------------------------------------------ #
    def test_scroll_down(self):
        driver = MagicMock()
        driver.get_window_size.return_value = {"width": 1080, "height": 1920}
        action = {"action": "scroll", "direction": "down"}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.get_window_size.assert_called_once()
        driver.swipe.assert_called_once_with(540, 1344, 540, 576, 400)
        assert result == "📜 滚动 down"

    def test_scroll_up(self):
        driver = MagicMock()
        driver.get_window_size.return_value = {"width": 720, "height": 1280}
        action = {"action": "scroll", "direction": "up"}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.get_window_size.assert_called_once()
        driver.swipe.assert_called_once_with(360, 384, 360, 896, 400)
        assert result == "📜 滚动 up"

    def test_scroll_default_direction_is_down(self):
        driver = MagicMock()
        driver.get_window_size.return_value = {"width": 1000, "height": 2000}
        action = {"action": "scroll"}

        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.swipe.assert_called_once_with(500, 1400, 500, 600, 400)
        assert result == "📜 滚动 down"

    # ------------------------------------------------------------------ #
    # back / home
    # ------------------------------------------------------------------ #
    def test_back(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        result = md.execute_action({"action": "back"})

        driver.back.assert_called_once()
        assert result == "↩️ 返回"

    def test_home(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        result = md.execute_action({"action": "home"})

        driver.press_keycode.assert_called_once_with(3)
        assert result == "🏠 回桌面"

    # ------------------------------------------------------------------ #
    # open_app
    # ------------------------------------------------------------------ #
    def test_open_app_package_from_target(self):
        driver = MagicMock()
        action = {
            "action": "open_app",
            "target": {"package": "com.target.pkg"},
        }
        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.activate_app.assert_called_once_with("com.target.pkg")
        assert result == "📱 打开应用 com.target.pkg"

    def test_open_app_package_from_action(self):
        driver = MagicMock()
        action = {
            "action": "open_app",
            "package": "com.action.pkg",
            "target": {},
        }
        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.activate_app.assert_called_once_with("com.action.pkg")
        assert result == "📱 打开应用 com.action.pkg"

    def test_open_app_package_from_target_text(self):
        driver = MagicMock()
        action = {
            "action": "open_app",
            "target": {"text": "com.text.pkg"},
        }
        md = MobileDriver(driver)
        result = md.execute_action(action)

        driver.activate_app.assert_called_once_with("com.text.pkg")
        assert result == "📱 打开应用 com.text.pkg"

    # ------------------------------------------------------------------ #
    # done
    # ------------------------------------------------------------------ #
    def test_done_with_summary(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        result = md.execute_action(
            {"action": "done", "summary": "已完成操作"}
        )
        assert result == "✅ 已完成操作"
        # 不应调用任何 driver 方法
        driver.back.assert_not_called()
        driver.swipe.assert_not_called()

    def test_done_without_summary(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        result = md.execute_action({"action": "done"})
        assert result == "✅ 任务完成"

    # ------------------------------------------------------------------ #
    # 未知动作 / target 校验
    # ------------------------------------------------------------------ #
    def test_unknown_action_raises(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        with pytest.raises(ValueError, match=r"未知动作: unknown"):
            md.execute_action({"action": "unknown"})

    def test_target_missing_locator_raises(self):
        driver = MagicMock()
        md = MobileDriver(driver)
        with pytest.raises(ValueError, match=r"target 缺定位信息"):
            md.execute_action({"action": "click", "target": {}})

    # ------------------------------------------------------------------ #
    # DryDriver
    # ------------------------------------------------------------------ #
    def test_dry_driver_page_source(self):
        xml = "<root><child>text</child></root>"
        dry = DryDriver(xml)
        assert dry.page_source() == xml

    def test_dry_driver_execute_action(self):
        xml = "<hierarchy></hierarchy>"
        dry = DryDriver(xml)
        action = {"action": "click", "target": {"text": "按钮"}}
        result = dry.execute_action(action)
        assert result == "[dry-run] 执行: {'action': 'click', 'target': {'text': '按钮'}}"

    def test_dry_driver_does_not_touch_driver(self):
        xml = "<hierarchy></hierarchy>"
        dry = DryDriver(xml)
        # 多次调用均不应抛出异常，且不执行任何真实 driver 调用
        for action in [
            {"action": "click", "target": {"text": "x"}},
            {"action": "input", "target": {"resource_id": "id"}, "text": "t"},
            {"action": "scroll"},
        ]:
            result = dry.execute_action(action)
            assert result.startswith("[dry-run] 执行:")
