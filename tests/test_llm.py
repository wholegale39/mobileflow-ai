"""测试 llm 模块:JSON 解析、多动作协议、边界情况。"""
from __future__ import annotations

import pytest

from mobileflow.llm import LlmClient


class TestParseJson:
    """测试 _parse_json 容错解析。"""

    def test_clean_json(self):
        raw = '{"action": "click", "target": {"text": "微信"}}'
        result = LlmClient._parse_json(raw)
        assert result["action"] == "click"
        assert result["target"]["text"] == "微信"

    def test_json_with_fencing(self):
        raw = '```json\n{"action": "done"}\n```'
        result = LlmClient._parse_json(raw)
        assert result["action"] == "done"

    def test_json_with_prefix(self):
        raw = '好的，我决定了：{"action": "scroll", "direction": "down"}'
        result = LlmClient._parse_json(raw)
        assert result["action"] == "scroll"
        # target 可能不存在，不强制要求

    def test_json_with_suffix(self):
        raw = '{"action": "input", "text": "hello"} 这样就对了'
        result = LlmClient._parse_json(raw)
        assert result["action"] == "input"

    def test_no_json_braces(self):
        with pytest.raises(ValueError, match="LLM 输出无 JSON"):
            LlmClient._parse_json("没有括号")

    def test_malformed_json(self):
        with pytest.raises(ValueError):
            LlmClient._parse_json('{"action": incomplete')

    def test_missing_action(self):
        with pytest.raises(ValueError, match="JSON 缺 action 字段"):
            LlmClient._parse_json('{"foo": "bar"}')

    def test_nested_json(self):
        raw = '{"action": "drag", "from": {"text": "A"}, "to": {"text": "B"}}'
        result = LlmClient._parse_json(raw)
        assert result["action"] == "drag"
        assert result["from"]["text"] == "A"
        assert result["to"]["text"] == "B"


class TestActionProtocols:
    """验证所有新增动作协议能被正确解析。"""

    @pytest.mark.parametrize("action_type,target", [
        ("click", {"text": "按钮"}),
        ("long_click", {"text": "长按"}),
        ("double_click", {"text": "双击"}),
        ("drag", {"from": {"text": "源"}, "to": {"text": "目标"}}),
        ("coordinate_click", {}),
        ("input_key", {}),
        ("wait", {"text": "加载中", "gone": True}),
        ("wait", {"text": "出现", "gone": False}),
    ])
    def test_all_actions_parseable(self, action_type, target):
        import json
        raw = json.dumps({"action": action_type, "target": target})
        result = LlmClient._parse_json(raw)
        assert result["action"] == action_type


class TestLlmClientInit:
    """测试初始化与环境变量读取。"""

    def test_defaults(self, monkeypatch):
        # Don't set env vars - let them be unset so defaults kick in
        monkeypatch.delenv("MOBILEFLOW_BASE_URL", raising=False)
        monkeypatch.delenv("MOBILEFLOW_API_KEY", raising=False)
        monkeypatch.delenv("MOBILEFLOW_MODEL", raising=False)
        # 注入假 key 仅让 openai 客户端能实例化（测试不发起真实调用）
        monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-test-fake-for-ci")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-for-ci")
        client = LlmClient()
        assert client.model == "glm-5.2"
        assert client.max_tokens == 300


class TestDecideAction:
    """测试 decide_action 的 system prompt 包含新动作协议。"""

    def test_system_prompt_includes_new_actions(self, monkeypatch):
        """验证 system prompt 包含 long_click/double_click/drag/coordinate_click/wait。"""
        calls = []
        def mock_chat(self_inst, system, user):
            calls.append((system, user))
            return '{"action": "done", "summary": "test"}'

        monkeypatch.setattr(LlmClient, "chat", mock_chat)
        monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-test-fake-for-ci")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-for-ci")
        client = LlmClient()
        client.decide_action("UI", "任务")

        assert len(calls) == 1
        system = calls[0][0]
        assert "long_click" in system
        assert "double_click" in system
        assert "drag" in system
        assert "coordinate_click" in system
        assert "input_key" in system
        assert "wait" in system
