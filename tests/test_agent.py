"""测试 agent 模块:决策循环、等待集成、新动作支持。"""
from __future__ import annotations

from unittest.mock import MagicMock

from mobileflow.agent import Agent
from mobileflow.driver import DryDriver, MobileDriver

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


# ---------- RAG 命中 / 技能回放 / 自愈路径 ----------

def test_agent_run_memory_rag_hit(monkeypatch):
    """精确哈希未命中但 RAG 召回相似链并回放成功 → via=memory_rag。"""
    llm = FakeLlmClient([{ "action": "done"}])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.return_value = "ok"

    from mobileflow.memory import MemoryEngine
    mem = MagicMock(spec=MemoryEngine)
    mem.lookup.return_value = None  # 精确未命中
    mem.stats.return_value = {"chains": 0, "stable": 0}

    agent = Agent(llm, driver, max_steps=5, memory=mem, skills=None)
    # 让 _rag_recall 返回一条相似链
    def _rag_recall(task):
        return {"task": "相似任务", "similarity": 0.35,
                "actions": [{"action": "done"}]}
    monkeypatch.setattr(agent, "_rag_recall", _rag_recall)

    result = agent.run("某任务")
    assert result["via"] == "memory_rag"
    assert "0.35" in result["summary"]
    assert llm.call_count == 0  # RAG 命中不走 LLM


def test_agent_run_memory_exact_hit(monkeypatch):
    """精确哈希命中 → via=memory。"""
    llm = FakeLlmClient([])
    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.return_value = "ok"
    from mobileflow.memory import MemoryEngine
    mem = MagicMock(spec=MemoryEngine)
    mem.lookup.return_value = [{"action": "done"}]
    mem.stats.return_value = {"chains": 1, "stable": 1}
    agent = Agent(llm, driver, max_steps=5, memory=mem, skills=None)
    result = agent.run("已记任务")
    assert result["via"] == "memory"
    assert llm.call_count == 0


def test_agent_run_self_heal_on_driver_failure(monkeypatch):
    """driver 执行抛错 → 自愈分支被触发(recoverer 返回恢复动作)。"""
    llm = FakeLlmClient([{"action": "click", "target": {"text": "btn"}}])
    driver = MagicMock()
    driver.page_source.return_value = SAMPLE_UI
    driver.execute_action.side_effect = RuntimeError("元素不可点击")
    driver.screenshot_b64.return_value = None

    healer = MagicMock()
    # 自愈器建议一个恢复动作
    healer.recover.return_value = {"action": "click", "target": {"text": "btn"}}
    # 第1次 execute_action(原动作)抛错 → 触发自愈; 第2次(恢复动作)成功; 第3次(重试原)成功
    driver.execute_action.side_effect = [RuntimeError("元素不可点击"), "recovered", "ok"]

    agent = Agent(llm, driver, max_steps=5, healer=healer, skills=None)
    agent.run("自愈场景")
    # 核心断言: 失败后自愈分支被触发
    assert healer.recover.called
