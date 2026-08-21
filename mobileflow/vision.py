"""多模态截图通道 —— 可选增强。

UI 树为主决策，截图通道补充视觉信息（复杂界面/图形元素/验证结果）。
默认关闭（--vision 开启），保持 GLM-5.2 纯文本决策的轻量路径。
截图描述用多模态模型（默认 agnes-2.5-pro，模型可配置）。

提供两种模式：
- describe_screenshot: 文字要点描述（主决策补充）
- analyze_screenshot: 结构化元素列表（含坐标，供纯视觉定位/点击）
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any


class VisionChannel:
    """截图理解通道：driver 截图 → 多模态模型 → 文本/结构供决策。"""

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
        return self._call_vision(image_b64, self._describe_prompt())

    def analyze_screenshot(self, image_b64: str) -> list[dict[str, Any]]:
        """截图 → 结构化元素列表（含坐标），供纯视觉定位/点击。

        Returns:
            [{"name": "购买", "x": 540, "y": 1200, "type": "button",
              "note": "红色按钮，底部居中"}, ...]
            返回元素列表；视觉模型无法识别时返回空列表。
        """
        raw = self._call_vision(image_b64, self._analyze_prompt())
        return self._parse_elements(raw)

    # ---------- 内部 ----------

    def _call_vision(self, image_b64: str, prompt: str) -> str:
        """调用多模态视觉模型，返回文本 content。"""
        env_key = self.api_key
        if not env_key:
            try:
                with open("/opt/data/.env", encoding="utf-8") as _f:
                    for line in _f:
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
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }],
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

    @staticmethod
    def _describe_prompt() -> str:
        return ("这是手机屏幕截图。用中文列出界面上对自动化操作有用的要点："
                "当前页面名称、主要按钮/输入框/列表项（按位置从上到下），3-5 条，简洁。")

    @staticmethod
    def _analyze_prompt() -> str:
        return (
            "这是手机屏幕截图。识别界面上所有可交互元素，输出【纯 JSON 数组】，每个元素一个对象：\n"
            '{"name": "显示文本或用途", "x": 屏幕中心x坐标(整数), "y": 屏幕中心y坐标(整数), '
            '"type": "button|input|text|list|icon", "note": "简短描述"}\n'
            "只输出 JSON 数组，不要任何解释或代码块。坐标基于整张截图的左上角原点。"
            "只列出明确可点击/可输入/可识别的元素，最多 20 个。无元素时输出空数组 []。"
        )

    @staticmethod
    def _parse_elements(raw: str) -> list[dict[str, Any]]:
        """从视觉模型输出中解析元素列表。"""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                out.append({
                    "name": str(item.get("name", "")),
                    "x": int(item.get("x", 0)),
                    "y": int(item.get("y", 0)),
                    "type": str(item.get("type", "")),
                    "note": str(item.get("note", "")),
                })
            except (TypeError, ValueError):
                continue
        return out


def format_vision_block(description: str) -> str:
    """视觉描述 → 决策 prompt 附加块。"""
    return f"\n[截图要点（视觉通道）]\n{description}" if description else ""
