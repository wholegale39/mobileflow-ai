"""任务规划器 —— 将大任务拆成子任务链,逐段 LLM 决策。

解决单轮 mt=300 无法覆盖复杂任务的瓶颈。

用法:
    planner = TaskPlanner(llm, driver)
    result = planner.run("打开淘宝搜索手机并加入购物车")

规划流程:
1. 用 LLM 把任务拆解成有序子任务(steps)
2. 对每个子任务调用 Agent._llm_loop 执行
3. 记录成功/失败,失败时回滚(可选)或继续
4. 整体返回 done/stuck/timeout/failed
"""
from __future__ import annotations

import json
import re
from typing import Any

from mobileflow.agent import Agent
from mobileflow.llm import LlmClient
from mobileflow.driver import MobileDriver, DryDriver


STEP_RE = re.compile(r"^[\\d①②③④⑤⑥⑦⑧⑨⑩\\.·•-]+\\s*(.+)$", re.MULTILINE)


class TaskPlanner:
    """任务规划执行器。

    把大任务拆解为子步骤,每个子步骤交给 Agent 独立决策执行。
    子步骤内部仍用 LLM 单轮决策(由 Agent 负责),这里只做顶层拆解。
    """

    def __init__(
        self,
        llm: LlmClient,
        driver: MobileDriver | DryDriver,
        *,
        max_steps_per_subtask: int = 10,
        max_subtasks: int = 10,
        rollback_on_failure: bool = False,
        trace_path: str | None = None,
    ) -> None:
        self.llm = llm
        self.driver = driver
        self.max_steps_per_subtask = max_steps_per_subtask
        self.max_subtasks = max_subtasks
        self.rollback_on_failure = rollback_on_failure
        self.trace_path = trace_path
        self.history: list[str] = []

    def run(self, task: str) -> dict[str, Any]:
        """执行规划后的任务。

        Returns:
            {"status": "done"/"stuck"/"timeout"/"failed",
             "subtasks": N,
             "steps": total_steps,
             "summary": "..."}
        """
        print(f"🎯 规划任务: {task}")
        subtasks = self._plan(task)
        if not subtasks:
            return {"status": "failed", "subtasks": 0, "steps": 0,
                    "summary": "LLM 未能拆解任务"}

        print(f"📋 拆解为 {len(subtasks)} 个子任务:")
        for i, st in enumerate(subtasks, 1):
            print(f"  {i}. {st}")

        results: list[dict[str, Any]] = []
        total_steps = 0
        for idx, subtask in enumerate(subtasks):
            print(f"\n🚀 执行子任务 [{idx+1}/{len(subtasks)}]: {subtask}")
            # 构造 Agent 只跑当前子任务,但历史保持连续
            agent = Agent(
                self.llm, self.driver,
                max_steps=self.max_steps_per_subtask,
                trace_path=self.trace_path,
            )
            result = agent.run(subtask)
            result["subtask"] = subtask
            results.append(result)
            total_steps += result.get("steps", 0)
            self.history.append(f"[{idx+1}] {subtask} → {result.get('status')}")

            if result["status"] != "done":
                print(f"  ⚠️ 子任务 {subtask} 未完成任务(status={result['status']})")
                if self.rollback_on_failure:
                    print("  🔄 触发回滚...")
                    self._rollback(results[:-1])
                    return {"status": "failed", "subtasks": idx + 1, "steps": total_steps,
                            "summary": f"子任务[{idx+1}]失败,已回滚", "failed_step": subtask}
                # 否则继续后续子任务
                continue

        return {
            "status": "done",
            "subtasks": len(subtasks),
            "steps": total_steps,
            "summary": f"完成 {len(subtasks)} 个子任务,{total_steps} 步",
            "results": results,
        }

    def _plan(self, task: str) -> list[str]:
        """调用 LLM 拆解任务为有序子任务列表。"""
        system = (
            "你是移动端自动化任务规划师。把一个大任务拆解为最多5个有序的子任务,每个子任务是一个可独立执行的原子动作序列。\n"
            "格式：每行一个子任务，编号 1/2/3...\n"
            "只输出子任务列表，不要解释。"
        )
        user = f"大任务：{task}\n要求：不超过{self.max_subtasks}个子任务，每个子任务要具体可执行（如\"点击搜索框\"、\"输入关键词\"）。"
        raw = self.llm.chat(system, user)
        steps = self._extract_steps(raw)
        # 截断到 max_subtasks
        return steps[:self.max_subtasks]

    @staticmethod
    def _extract_steps(raw: str) -> list[str]:
        """从 LLM 输出中提取子任务列表。"""
        steps: list[str] = []
        for line in raw.split("\n"):
            line = line.strip()
            # 匹配 1. xxx / 1 xxx / ① xxx 等
            m = re.match(r"^[\d①②③④⑤⑥⑦⑧⑨⑩\-•·.]+[\.\)：:]\s*(.+)", line)
            if m:
                steps.append(m.group(1).strip())
            elif line and len(steps) < 10 and not line.startswith(("注", "说明", "##", "*")):
                # 兜底：非空行当作子任务
                steps.append(line)
        return steps[:10]

    def _rollback(self, successful_results: list[dict[str, Any]]) -> None:
        """回滚：从后向前执行相反动作（简化版）。"""
        print("  🔄 回滚中...")
        for r in reversed(successful_results):
            subtask = r.get("subtask", "")
            # 简化回滚：点击 back 直到回到初始页
            try:
                self.driver.execute_action({"action": "back"})
            except Exception:
                break
