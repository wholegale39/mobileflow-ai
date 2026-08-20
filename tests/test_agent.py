"""测试 agent 模块:决策循环、等待集成、新动作支持。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from mobileflow.agent import Agent
from mobileflow.llm import LlmClient
from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.memory import MemoryEngine
from mobileflow.skills import SkillLibrary


SAMPLE_UI = "<root><node text='测试'/></root>"
SAMPLE_UI_2 = "<root><node text='测试2'/></root>"


class FakeLlmClient:
    """模拟 LLM 客户端。"""

    def __init__(self, actions: list[dict]):
        self.actions = actions
        self.call_count = 0

    def chat(self, system: str, user: str) -> str:
        if self.call_count < len(self.actions):
            action = self.actions[self.call_count]
            self.call_count += 1
            return f'{{"action": "{action.get("action", "done")}", "target": {action.get("target", {})}}}'
        return '{"action": "done", "summary": "完成"}'

    def decide_action(self, ui_text: str, task: str, history=None):
        if self.call_count < len(self.actions):
            action = self.actions[self.call_count]
            self.call_count += 1
            return action
        return {"action": "done", "summary": "完成"}


def test_agent_run_done_on_first_step():
    llm = FakeLlmClient([{"action": "done", "summary": "已完成"}])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.return_value = "✅ 任务完成"

    agent = Agent(llm, driver, max_steps=5)
    result = agent.run("测试任务")

    assert result["status"] == "done"
    assert result["steps"] == 1


def test_agent_run_timeout():
    llm = FakeLlmClient([
        {"action": "click", "target": {"text": "A"}},
        {"action": "click", "target": {"text": "B"}},
    ])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "👆 点击 A",
        "👆 点击 B",
    ]

    agent = Agent(llm, driver, max_steps=2)
    result = agent.run("超时测试")

    assert result["status"] == "timeout"
    assert result["steps"] == 2


def test_agent_run_stuck_detection():
    """UI 连续 N 步无变化时判定停滞。"""
    llm = FakeLlmClient([
        {"action": "click", "target": {"text": "A"}},
        {"action": "click", "target": {"text": "A"}},
    ])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.return_value = "👆 点击 A"

    agent = Agent(llm, driver, max_steps=10, stuck_threshold=2, settle_wait=0.01)
    result = agent.run("停滞测试")

    assert result["status"] == "stuck"


def test_agent_run_long_click_action():
    llm = FakeLlmClient([
        {"action": "long_click", "target": {"text": "长按项"}},
        {"action": "done", "summary": "长按完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "🖐️ 长按 「长按项」",
        "✅ 长按完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("长按测试")

    assert result["status"] == "done"


def test_agent_run_coordinate_click():
    llm = FakeLlmClient([
        {"action": "coordinate_click", "x": 540, "y": 1000},
        {"action": "done", "summary": "坐标点击完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "📍 点击坐标 (540, 1000)",
        "✅ 坐标点击完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("坐标点击测试")

    assert result["status"] == "done"
    assert result["steps"] == 2


def test_agent_run_wait_action():
    llm = FakeLlmClient([
        {"action": "wait", "target": {"text": "加载中", "gone": True}},
        {"action": "done", "summary": "等待完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "⏳ 等待元素消失 ✓",
        "✅ 等待完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("等待测试")

    assert result["status"] == "done"


def test_agent_run_input_key():
    llm = FakeLlmClient([
        {"action": "input_key", "keycode": 66},
        {"action": "done", "summary": "按键完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "⌨️ 按键 Enter",
        "✅ 按键完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("按键测试")

    assert result["status"] == "done"


def test_agent_run_drag():
    llm = FakeLlmClient([
        {"action": "drag", "from": {"text": "源"}, "to": {"text": "目标"}},
        {"action": "done", "summary": "拖动完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "↔️ 拖动 「源」 → 「目标」",
        "✅ 拖动完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("拖动测试")

    assert result["status"] == "done"


def test_agent_run_double_click():
    llm = FakeLlmClient([
        {"action": "double_click", "target": {"text": "双击项"}},
        {"action": "done", "summary": "双击完成"},
    ])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = [
        "👆👆 双击 「双击项」",
        "✅ 双击完成",
    ]

    agent = Agent(llm, driver, max_steps=5, settle_wait=0.01)
    result = agent.run("双击测试")

    assert result["status"] == "done"


def test_agent_trace_path():
    llm = FakeLlmClient([{"action": "done", "summary": "测试"}])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.return_value = "✅ 测试"

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        trace_path = f.name

    try:
        agent = Agent(llm, driver, trace_path=trace_path)
        agent.run("轨迹测试")

        with open(trace_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        import json
        entry = json.loads(lines[0])
        assert "ts" in entry
        assert "task" in entry
        assert "action" in entry
    finally:
        import os
        os.unlink(trace_path)


def test_agent_run_with_vision():
    """有 vision 通道时的行为。"""
    llm = FakeLlmClient([{"action": "done", "summary": "完成"}])
    driver = MagicMock(spec=MobileDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.screenshot_b64.return_value = "iVBORw0KGgo="
    driver.execute_action.return_value = "✅ 完成"

    vision = MagicMock()
    vision.describe_screenshot.return_value = "这是一个按钮"

    agent = Agent(llm, driver, vision=vision, max_steps=1, settle_wait=0.01)
    result = agent.run("视觉测试")

    assert result["status"] == "done"
    vision.describe_screenshot.assert_called_once()


def test_agent_run_dry_driver():
    """DryDriver 模式下的基本运行。"""
    llm = FakeLlmClient([{"action": "done", "summary": "dry 测试"}])
    driver = DryDriver(SAMPLE_UI)

    agent = Agent(llm, driver, max_steps=1)
    result = agent.run("dry 测试")

    assert result["status"] == "done"
