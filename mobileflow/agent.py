"""Agent 主循环 —— 截图/UI树 → GLM-5.2 决策 → Appium 执行 → 验证。

循环直到：done 动作 / 最大步数 / 连续重试超限。
"""
from __future__ import annotations

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
    ) -> None:
        self.llm = llm
        self.driver = driver
        self.max_steps = max_steps
        self.settle_wait = settle_wait
        self.history: list[str] = []
        self._same_state_streak = 0

    def run(self, task: str) -> dict[str, Any]:
        """执行任务，返回结果报告。"""
        print(f"🎯 任务: {task}")
        for step in range(1, self.max_steps + 1):
            ui_text = compress_page_source(self.driver.page_source())
            print(f"\n—— 第 {step} 步 ——")

            action = self.llm.decide_action(ui_text, task, self.history)
            result = self.driver.execute_action(action)
            print(f"决策: {action}")
            print(f"执行: {result}")

            self.history.append(f"{action.get('action')}: {result}")

            if action.get("action") == "done":
                return {"status": "done", "steps": step, "summary": action.get("summary", "")}

            time.sleep(self.settle_wait)  # 等界面稳定

        return {"status": "timeout", "steps": self.max_steps, "summary": "达到最大步数"}
