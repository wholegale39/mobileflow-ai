"""Agent 主循环 —— UI树(page source) → GLM-5.2 决策 → Appium 执行 → 验证。

循环直到：done 动作 / 最大步数 / 连续重试超限（UI 停滞检测）。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.llm import LlmClient
from mobileflow.ui_tree import compress_page_source


class Agent:
    def __init__(
        self,
        llm: LlmClient,
        driver: MobileDriver | DryDriver,
        max_steps: int = 20,
        settle_wait: float = 1.5,
        stuck_threshold: int = 3,
    ) -> None:
        self.llm = llm
        self.driver = driver
        self.max_steps = max_steps
        self.settle_wait = settle_wait
        self.stuck_threshold = stuck_threshold  # 同一 UI 连续出现 N 次判定停滞
        self.history: list[str] = []
        self._last_ui_hash: str | None = None
        self._same_state_streak = 0

    def run(self, task: str) -> dict[str, Any]:
        """执行任务，返回结果报告。"""
        print(f"🎯 任务: {task}")
        for step in range(1, self.max_steps + 1):
            ui_text = compress_page_source(self.driver.page_source())
            print(f"\n—— 第 {step} 步 ——")

            # UI 停滞检测：同一界面连续 N 次 → 提前终止，避免空转
            ui_hash = hashlib.md5(ui_text.encode()).hexdigest()
            if ui_hash == self._last_ui_hash:
                self._same_state_streak += 1
            else:
                self._same_state_streak = 0
                self._last_ui_hash = ui_hash
            if self._same_state_streak >= self.stuck_threshold:
                return {
                    "status": "stuck",
                    "steps": step,
                    "summary": f"UI 连续 {self.stuck_threshold} 步无变化，判定停滞",
                }

            action = self.llm.decide_action(ui_text, task, self.history)
            if not isinstance(action, dict) or not action.get("action"):
                raise ValueError(f"LLM 返回非法动作: {action!r}")

            try:
                result = self.driver.execute_action(action)
            except Exception as e:  # 执行异常 → 记录并让 LLM 下一步调整
                result = f"⚠️ 执行失败: {e}"
            print(f"决策: {action}")
            print(f"执行: {result}")

            self.history.append(f"{action.get('action')}: {result}")

            if action.get("action") == "done":
                return {"status": "done", "steps": step, "summary": action.get("summary", "")}

            time.sleep(self.settle_wait)  # 等界面稳定

        return {"status": "timeout", "steps": self.max_steps, "summary": "达到最大步数"}
