import json
import urllib.error

import pytest
from unittest.mock import MagicMock, patch

from mobileflow.vision import VisionChannel, format_vision_block


def _chan(**kw):
    defaults = dict(base_url="https://x/v1", api_key="sk-key", model="agnes-2.5-pro")
    defaults.update(kw)
    return VisionChannel(**defaults)


class TestFormatVisionBlock:
    def test_with_description(self):
        assert format_vision_block("要点") == "\n[截图要点（视觉通道）]\n要点"

    def test_empty_description(self):
        assert format_vision_block("") == ""
        assert format_vision_block(None) == ""


class TestDescribeScreenshot:
    @patch("mobileflow.vision.urllib.request.urlopen")
    def test_success_payload_and_return(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "  主页 / 登录按钮  "}}]
        }).encode()
        mock_urlopen.return_value = mock_resp

        ch = _chan()
        res = ch.describe_screenshot("img-base64")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["model"] == "agnes-2.5-pro"
        msgs = payload["messages"]
        assert isinstance(msgs, list) and len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert payload["reasoning_effort"] == "none"
        content = msgs[0]["content"]
        assert any(c.get("type") == "image_url" for c in content)
        img = [c for c in content if c.get("type") == "image_url"][0]
        assert img["image_url"]["url"].startswith("data:image/png;base64,")
        assert res == "主页 / 登录按钮"

    @patch("mobileflow.vision.urllib.request.urlopen")
    def test_http_error_raises_runtime_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://x/v1", 401, "bad", {}, None
        )
        with pytest.raises(RuntimeError):
            _chan().describe_screenshot("x")

    def test_missing_key_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
        monkeypatch.setenv("MOBILEFLOW_VISION_BASE_URL", "https://x/v1")
        # .env 兜底路径也要失效，才能触达「无 key」分支
        monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("no env")))
        ch = VisionChannel(base_url="https://x/v1", api_key="")
        with pytest.raises(RuntimeError):
            ch.describe_screenshot("x")

    @patch("mobileflow.vision.urllib.request.urlopen")
    def test_urlopen_exception_propagates(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionRefusedError("boom")
        with pytest.raises(ConnectionRefusedError):
            _chan().describe_screenshot("x")