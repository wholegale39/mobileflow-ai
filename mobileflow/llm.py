"""GLM-5.2 决策模块 —— OpenAI 兼容调用，输出 JSON 动作。

适配商汤渠道约束：
- reasoning_effort=none（思考模式 content 必空）
- max_tokens 控制在 300 内（workspace 配额按 max_tokens 预留扣减，大值必 429）
- 单轮单请求，调用方负责节流
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI


class LlmClient:
    """OpenAI 兼容 LLM 客户端（默认商汤 GLM-5.2）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 300,
    ) -> None:
        self.base_url = base_url or os.environ.get(
            "MOBILEFLOW_BASE_URL", "https://token.sensenova.cn/v1"
        )
        self.api_key = api_key or os.environ.get("MOBILEFLOW_API_KEY", "")
        self.model = model or os.environ.get("MOBILEFLOW_MODEL", "glm-5.2")
        self.max_tokens = max_tokens
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=60)

    def chat(self, system: str, user: str) -> str:
        """单轮文本对话（直出模式）。"""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            reasoning_effort="none",  # 商汤思考模型必须关，否则 content 空
            max_tokens=self.max_tokens,
        )
        content = resp.choices[0].message.content or ""
        if not content.strip():
            raise RuntimeError(f"LLM 返回空 content (finish={resp.choices[0].finish_reason})")
        return content.strip()

    def decide_action(self, ui_text: str, task: str, history: list[str] | None = None) -> dict[str, Any]:
        """UI 树文本 + 任务 → 单个 JSON 动作。"""
        history_block = "\n".join(f"- {h}" for h in (history or [])[-8:]) or "（无）"
        system = (
            "你是移动端自动化 Agent 的决策大脑。根据当前屏幕的 UI 树和任务目标，"
            "输出【一个】JSON 动作。只输出 JSON，不要任何解释或代码块标记。\n"
            "动作协议：\n"
            '{"action": "click", "target": {"text": "..."}} 点击含该文本的元素\n'
            '{"action": "click", "target": {"resource_id": "..."}} 点击指定 id 元素\n'
            '{"action": "click", "target": {"index": N}} 点击第 N 个元素\n'
            '{"action": "long_click", "target": {"text": "..."}} 长按元素\n'
            '{"action": "double_click", "target": {"text": "..."}} 双击元素\n'
            '{"action": "drag", "from": {...}, "to": {...}} 拖动元素到目标\n'
            '{"action": "coordinate_click", "x": 540, "y": 1200} 点击屏幕坐标\n'
            '{"action": "input", "target": {"resource_id": "..." | "text": "..."}, "text": "输入内容"}\n'
            '{"action": "input_key", "keycode": 66} 按键（66=Enter, 4=Back, 3=Home）\n'
            '{"action": "swipe", "start": [x, y], "end": [x, y]}\n'
            '{"action": "scroll", "direction": "down" | "up"}\n'
            '{"action": "wait", "target": {"text": "...", "gone": true}} 等待元素消失\n'
            '{"action": "wait", "target": {"text": "..."}} 等待元素出现\n'
            '{"action": "back"}\n'
            '{"action": "home"}\n'
            '{"action": "open_app", "package": "应用包名"}\n'
            '{"action": "done", "summary": "任务已完成说明"}  # 仅当任务确实完成\n'
            "规则：优先用 text 定位；text 不明显才用 resource_id；都没有才用 index。"
            "目标不在当前屏幕时用 scroll/swipe/back 寻找。"
        )
        user = (
            f"任务：{task}\n\n"
            f"已执行步骤：\n{history_block}\n\n"
            f"当前屏幕 UI 树（已压缩）：\n{ui_text}"
        )
        raw = self.chat(system, user)
        return self._parse_json(raw)

    @staticmethod
    def _action_to_desc(action: dict[str, Any]) -> str:
        """把动作 dict 转成人类可读的一句话（供恢复器分析失败用）。"""
        act = action.get("action", "")
        t = action.get("target") or {}
        if act in ("click", "long_click", "double_click"):
            if t.get("text"):
                return f"{act}(text={t['text']!r})"
            if t.get("resource_id"):
                return f"{act}(resource_id={t['resource_id']!r})"
            if t.get("index") is not None:
                return f"{act}(index={t['index']})"
        if act == "input":
            return f"input(text={action.get('text')!r}) -> {t}"
        if act == "coordinate_click":
            return f"coordinate_click(x={action.get('x')}, y={action.get('y')})"
        if act == "swipe":
            return f"swipe({action.get('start')}→{action.get('end')})"
        if act == "drag":
            return f"drag({action.get('from')}→{action.get('to')})"
        if act == "scroll":
            return f"scroll({action.get('direction')})"
        if act == "input_key":
            return f"input_key(keycode={action.get('keycode')})"
        return f"{act}({action})"

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """容错解析 LLM 输出的 JSON（去掉代码块围栏/前后废话）。"""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        # 找第一个 { 到最后一个 }
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"LLM 输出无 JSON: {raw[:120]}")
        try:
            obj = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {e} — {raw[:120]}")
        if not isinstance(obj, dict) or "action" not in obj:
            raise ValueError(f"JSON 缺 action 字段: {obj}")
        return obj
