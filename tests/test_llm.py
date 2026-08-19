import json
import re
from unittest.mock import MagicMock, patch

import pytest

from mobileflow.llm import LlmClient


class TestParseJson:
    def test_A1_带json围栏的合法JSON能解析(self):
        """A1: 带 ```json 代码块围栏的合法 JSON 能解析"""
        raw = '```json\n{"action": "click", "target": "button"}\n```'
        result = LlmClient._parse_json(raw)
        assert result == {"action": "click", "target": "button"}

    def test_A2_前后有废话文本能解析(self):
        """A2: 前后包含废话文本时仍能解析出 JSON"""
        raw = '好的，这是结果：\n{"action": "click", "target": "button"}\n以上是操作建议。'
        result = LlmClient._parse_json(raw)
        assert result == {"action": "click", "target": "button"}

    def test_A3_值里含嵌套花括号能解析(self):
        """A3: 值中含嵌套花括号时能正确解析"""
        raw = '{"action": "click", "target": {"index": 1}}'
        result = LlmClient._parse_json(raw)
        assert result == {"action": "click", "target": {"index": 1}}

    def test_A4_缺action字段抛ValueError(self):
        """A4: 缺少 action 字段的 JSON 抛 ValueError"""
        raw = '{"target": "button"}'
        with pytest.raises(ValueError):
            LlmClient._parse_json(raw)

    def test_A5_非法JSON抛ValueError(self):
        """A5: 非法 JSON 抛 ValueError"""
        raw = '{"action": "click", "target": "button"'
        with pytest.raises(ValueError):
            LlmClient._parse_json(raw)

    def test_A6_无花括号纯文本抛ValueError(self):
        """A6: 完全没有花括号的纯文本抛 ValueError"""
        raw = '这是一段没有任何 JSON 的纯文本说明'
        with pytest.raises(ValueError):
            LlmClient._parse_json(raw)


class TestChat:
    def test_B1_验证调用参数messages和reasoning_effort及max_tokens(self):
        """B1: 验证 create 调用参数：messages 含 system 和 user、reasoning_effort 为 none、max_tokens 正确"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test", model="m", max_tokens=500)
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(
                message=MagicMock(content='{"action": "click"}'),
                finish_reason="stop",
            )
        ]
        client.client.chat.completions.create = MagicMock(return_value=fake_response)

        client.chat("你是助手", "请点击")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "m"
        assert call_kwargs["reasoning_effort"] == "none"
        assert call_kwargs["max_tokens"] == 500
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "你是助手"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "请点击"

    def test_B2_返回content_strip结果(self):
        """B2: 返回 content.strip() 结果"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(
                message=MagicMock(content='  {"action": "click"}  \n'),
                finish_reason="stop",
            )
        ]
        client.client.chat.completions.create = MagicMock(return_value=fake_response)

        result = client.chat("sys", "usr")
        assert result == '{"action": "click"}'

    def test_B3_content为空或None抛RuntimeError含finish_reason(self):
        """B3: content 为 None 或空字符串时抛 RuntimeError，且消息含 finish_reason"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")

        # content 为 None
        fake_none = MagicMock()
        fake_none.choices = [
            MagicMock(
                message=MagicMock(content=None),
                finish_reason="length",
            )
        ]
        client.client.chat.completions.create = MagicMock(return_value=fake_none)
        with pytest.raises(RuntimeError) as exc_info_none:
            client.chat("sys", "usr")
        assert "length" in str(exc_info_none.value)

        # content 为空字符串
        fake_empty = MagicMock()
        fake_empty.choices = [
            MagicMock(
                message=MagicMock(content="   "),
                finish_reason="stop",
            )
        ]
        client.client.chat.completions.create = MagicMock(return_value=fake_empty)
        with pytest.raises(RuntimeError) as exc_info_empty:
            client.chat("sys", "usr")
        assert "stop" in str(exc_info_empty.value)


class TestDecideAction:
    def test_C1_system提示包含动作协议关键词与JSON_schema示例(self):
        """C1: 验证 system 提示包含动作协议关键词（action、click、swipe）与 JSON schema 示例"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")
        captured = {}

        def fake_chat(system, user):
            captured["system"] = system
            captured["user"] = user
            return '{"action": "done"}'

        client.chat = MagicMock(side_effect=fake_chat)

        client.decide_action("UI树文本", "完成任务")

        system_prompt = captured["system"]
        assert "action" in system_prompt
        assert "click" in system_prompt
        assert "swipe" in system_prompt
        assert "{" in system_prompt and "}" in system_prompt

    def test_C2_user提示包含任务文本UI树文本及后8条history(self):
        """C2: 验证 user 提示包含任务文本、UI 树文本，history 超过 8 条只取后 8 条"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")
        captured = {}

        def fake_chat(system, user):
            captured["system"] = system
            captured["user"] = user
            return '{"action": "done"}'

        client.chat = MagicMock(side_effect=fake_chat)

        history = [f"历史步骤{i}" for i in range(10)]
        client.decide_action("当前屏幕UI树", "点击登录按钮", history=history)

        user_prompt = captured["user"]
        assert "任务：" in user_prompt
        assert "点击登录按钮" in user_prompt
        assert "当前屏幕UI树" in user_prompt
        for item in [f"历史步骤{i}" for i in range(2, 10)]:
            assert item in user_prompt
        for item in [f"历史步骤0", "历史步骤1"]:
            assert item not in user_prompt

    def test_C3_通过mock_create返回JSON字符串验证decide_action返回dict(self):
        """C3: 通过 mock create 返回 JSON 字符串，验证 decide_action 返回该 dict"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(
                message=MagicMock(content='{"action": "click", "target": {"text": "登录"}}'),
                finish_reason="stop",
            )
        ]
        client.client.chat.completions.create = MagicMock(return_value=fake_response)

        result = client.decide_action("UI树", "点击登录")
        assert result == {"action": "click", "target": {"text": "登录"}}

    def test_C4_history为空时user提示含无(self):
        """C4: history 为空时 user 提示含“（无）”"""
        client = LlmClient(base_url="http://localhost:1234/v1", api_key="test")
        captured = {}

        def fake_chat(system, user):
            captured["system"] = system
            captured["user"] = user
            return '{"action": "done"}'

        client.chat = MagicMock(side_effect=fake_chat)

        client.decide_action("UI树", "任务", history=None)

        assert "（无）" in captured["user"]
