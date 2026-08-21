"""失败自愈 —— 执行出错时截屏分析并重规划。

闭环：动作执行失败 → 截图 → 视觉理解当前屏幕 → 交由 LLM 分析失败原因并给出恢复动作 → 执行恢复动作 → 重试验证。

把"僵化重试"升级为"分析后重规划"。
"""
from __future__ import annotations

from typing import Any

from mobileflow.llm import LlmClient
from mobileflow.vision import VisionChannel, format_vision_block


class SelfHealer:
    """失败恢复器：结合视觉 + LLM 分析执行失败并重规划。"""

    def __init__(
        self,
        llm: LlmClient,
        vision: VisionChannel | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.llm = llm
        # 自恢复可用独立视觉模型（如更便宜/更稳定的），否则复用 Agent 的 vision
        self.vision = vision
        self._fallback_llm_kwargs: dict[str, Any] = {}
        if base_url is not None:
            self._fallback_llm_kwargs["base_url"] = base_url
        if api_key is not None:
            self._fallback_llm_kwargs["api_key"] = api_key
        if model is not None:
            self._fallback_llm_kwargs["model"] = model

    def recover(
        self,
        *,
        ui_text: str,
        screenshot_b64: str | None,
        failed_action: dict[str, Any],
        error: Exception,
        task: str,
        history: list[str],
    ) -> dict[str, Any] | None:
        """分析失败并重规划。

        Returns:
            恢复动作 dict（执行后可重试原动作），或 None（无法恢复）。
        """
        # 1. 视觉理解当前屏幕（可选，缺则只用 UI 树）
        vision_block = ""
        if screenshot_b64 and self.vision:
            try:
                desc = self.vision.describe_screenshot(screenshot_b64)
                vision_block = format_vision_block(desc)
            except Exception:
                vision_block = ""

        # 2. 让 LLM 分析失败原因并给恢复动作
        action_desc = LlmClient._action_to_desc(failed_action)
        system = (
            "你是移动端自动化 Agent 的故障恢复专家。Agent 刚执行了一个动作但失败了，"
            "你需要根据失败信息和当前屏幕状态，输出【一个】恢复动作来把 Agent 带回可继续执行的状态。"
            "只输出 JSON，不要解释或代码块标记。\n"
            "动作协议（与主决策一致）：\n"
            '{"action": "click", "target": {"text": "..."}} 点击含该文本的元素\n'
            '{"action": "click", "target": {"resource_id": "..."}} 点击指定 id 元素\n'
            '{"action": "click", "target": {"index": N}} 点击第 N 个元素\n'
            '{"action": "coordinate_click", "x": 540, "y": 1200} 点击屏幕坐标\n'
            '{"action": "long_click", "target": {"text": "..."}} 长按元素\n'
            '{"action": "double_click", "target": {"text": "..."}} 双击元素\n'
            '{"action": "drag", "from": {...}, "to": {...}} 拖动元素到目标\n'
            '{"action": "input", "target": {...}, "text": "输入内容"}\n'
            '{"action": "input_key", "keycode": 66} 按键（66=Enter, 4=Back, 3=Home）\n'
            '{"action": "swipe", "start": [x, y], "end": [x, y]}\n'
            '{"action": "scroll", "direction": "down" | "up"}\n'
            '{"action": "wait", "target": {"text": "..."}} 等待元素出现\n'
            '{"action": "back"} 返回上一页\n'
            '{"action": "home"} 回桌面\n'
            '{"action": "open_app", "package": "应用包名"}\n'
            "如果确实无法恢复，输出：{\"action\": \"giveup\", \"reason\": \"...\"}。"
            "优先用视觉/文字能直接定位的方式；目标是让原失败动作有重新执行的机会。"
        )
        user = (
            f"任务：{task}\n\n"
            f"失败的动作为：{action_desc}\n"
            f"失败原因：{error}\n\n"
            f"已执行历史（最近）：\n" + ("\n".join(f"- {h}" for h in history[-8:]) or "（无）") + "\n\n"
            f"当前屏幕 UI 树（已压缩）：\n{ui_text}"
            f"{vision_block}"
        )

        # 3. 用主 LLM（或指定兜底 LLM）分析
        client = self._client()
        try:
            raw = client.chat(system, user)
            action = LlmClient._parse_json(raw)
        except Exception as e:
            print(f"  ⚠️ 恢复分析本身失败: {e}")
            return None

        if action.get("action") == "giveup":
            print(f"  🛑 恢复器判定无法恢复: {action.get('reason')}")
            return None
        return action

    def _client(self) -> LlmClient:
        if self._fallback_llm_kwargs:
            return LlmClient(**self._fallback_llm_kwargs)
        return self.llm
