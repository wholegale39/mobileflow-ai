"""多模态截图通道 —— 可选增强。

UI 树为主决策，截图通道补充视觉信息（复杂界面/图形元素/验证结果）。
默认关闭（--vision 开启），保持 GLM-5.2 纯文本决策的轻量路径。
截图描述用多模态模型（默认 agnes-2.5-pro，模型可配置）。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class VisionChannel:
    """截图理解通道：driver 截图 → 多模态模型描述 → 文本供决策。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 400,
    ) -> None:
        self.base_url = base_url or os.environ.get(
            "MOBILEFLOW_VISION_BASE_URL", "https://apihub.agnes-ai.com/v1"
        )
        self.api_key = api_key or os.environ.get("MOBILEFLOW_VISION_API_KEY", "")
        self.model = model or os.environ.get("MOBILEFLOW_VISION_MODEL", "agnes-2.5-pro")
        self.max_tokens = max_tokens

    def describe_screenshot(self, image_b64: str) -> str:
        """截图 base64 → 界面要点描述（中文，3-5 条）。"""
        env_key = self.api_key
        if not env_key:
            # 兜底：从 /opt/data/.env 读 AGNES_API_KEY
            try:
                for line in open("/opt/data/.env", encoding="utf-8"):
                    line = line.strip()
                    if line.startswith("AGNES_API_KEY="):
                        env_key = line.split("=", 1)[1].strip().strip('"')
                        break
            except OSError:
                pass
        if not env_key:
            raise RuntimeError("VisionChannel 缺 API key（设 MOBILEFLOW_VISION_API_KEY）")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "这是手机屏幕截图。用中文列出界面上对自动化操作有用的要点："
                            "当前页面名称、主要按钮/输入框/列表项（按位置从上到下），3-5 条，简洁。",
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
            "reasoning_effort": "none",
            "max_tokens": self.max_tokens,
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + env_key, "Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            d = json.loads(resp.read())
            return (d["choices"][0]["message"].get("content") or "").strip()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"视觉请求失败 HTTP {e.code}: {e.read().decode()[:150]}")


def format_vision_block(description: str) -> str:
    """视觉描述 → 决策 prompt 附加块。"""
    return f"\n[截图要点（视觉通道）]\n{description}" if description else ""
