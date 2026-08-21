"""测试 planner 与 agent 集成:规划器驱动 agent。"""
from __future__ import annotations

from unittest.mock import MagicMock

from mobileflow.driver import DryDriver
from mobileflow.llm import LlmClient
from mobileflow.planner import TaskPlanner


def test_planner_integration_with_mock():
    """端到端测试:planner 拆解 → agent 执行。"""
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = "1. 点击首页\n2. 搜索商品\n3. 加入购物车"
    llm.decide_action.return_value = {"action": "done", "summary": "完成"}

    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = "<root><node text='首页'/></root>"
    driver.execute_action.return_value = "✅ 完成"

    planner = TaskPlanner(llm, driver, max_steps_per_subtask=5)
    result = planner.run("打开淘宝搜索手机加入购物车")

    assert result["status"] == "done"
    assert result["subtasks"] == 3
    assert result["steps"] == 3  # 每个子任务1步


def test_planner_subtask_failure_continues():
    """子任务失败但不回滚时继续执行后续子任务。"""
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = "1. 成功步骤\n2. 失败步骤\n3. 后续步骤"
    llm.decide_action.return_value = {"action": "done", "summary": "完成"}

    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = "<root/>"
    call_count = [0]
    def execute_side_effect(action):
        call_count[0] += 1
        if call_count[0] == 2:  # 第二个子任务失败
            raise RuntimeError("网络错误")
        return "ok"
    driver.execute_action.side_effect = execute_side_effect

    planner = TaskPlanner(llm, driver, rollback_on_failure=False)
    result = planner.run("部分失败测试")

    assert result["status"] == "done"
    assert result["subtasks"] == 3


def test_planner_history_accumulation():
    """测试 planner 累积 history。"""
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = "1. 步骤A\n2. 步骤B"
    llm.decide_action.return_value = {"action": "done", "summary": "完成"}

    driver = MagicMock(spec=DryDriver)
    driver.page_source.return_value = "<root/>"
    driver.execute_action.return_value = "ok"

    planner = TaskPlanner(llm, driver)
    planner.run("历史测试")

    assert len(planner.history) == 2
    assert any("步骤A" in h for h in planner.history)
    assert any("步骤B" in h for h in planner.history)
