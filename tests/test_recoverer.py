"""测试 recoverer 自愈模块：失败分析重规划。"""
from __future__ import annotations

from unittest.mock import MagicMock

from mobileflow.llm import LlmClient
from mobileflow.recoverer import SelfHealer


def test_recover_produces_recover_action():
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = '{"action": "back"}'
    healer = SelfHealer(llm)
    action = healer.recover(
        ui_text="<root><node text='设置'/></root>",
        screenshot_b64=None,
        failed_action={"action": "click", "target": {"text": "购买"}},
        error=RuntimeError("element not found"),
        task="下单",
        history=["click: ok"],
    )
    assert action["action"] == "back"
    # LLM 收到的 prompt 应包含失败动作描述与错误
    prompt = llm.chat.call_args[0][1]
    assert "购买" in prompt
    assert "下单" in prompt


def test_recover_giveup_returns_none():
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = '{"action": "giveup", "reason": "无法恢复"}'
    healer = SelfHealer(llm)
    action = healer.recover(
        ui_text="<root/>",
        screenshot_b64=None,
        failed_action={"action": "click", "target": {"text": "x"}},
        error=RuntimeError("fail"),
        task="t",
        history=[],
    )
    assert action is None


def test_recover_uses_vision():
    llm = MagicMock(spec=LlmClient)
    llm.chat.return_value = '{"action": "click", "target": {"index": 0}}'
    vision = MagicMock()
    vision.describe_screenshot.return_value = "页面显示确认弹窗，有确定按钮"
    healer = SelfHealer(llm, vision=vision)
    healer.recover(
        ui_text="<root/>",
        screenshot_b64="imgdata",
        failed_action={"action": "click", "target": {"text": "ok"}},
        error=RuntimeError("stale"),
        task="t",
        history=[],
    )
    vision.describe_screenshot.assert_called_once_with("imgdata")
    user_prompt = llm.chat.call_args[0][1]
    assert "确认弹窗" in user_prompt


def test_action_to_desc():
    assert LlmClient._action_to_desc({"action": "click", "target": {"text": "微信"}}) == "click(text='微信')"
    assert "coordinate_click" in LlmClient._action_to_desc({"action": "coordinate_click", "x": 100, "y": 200})
