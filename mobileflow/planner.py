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

        # 一个持久 Agent 跨所有子任务复用：history / UI 上下文连续，避免子任务间"断片"
        agent = Agent(
            self.llm, self.driver,
            max_steps=self.max_steps_per_subtask,
            trace_path=self.trace_path,
        )
        results: list[dict[str, Any]] = []
        total_steps = 0
        succeeded_indices: list[int] = []
        for idx, subtask in enumerate(subtasks):
            print(f"\n🚀 执行子任务 [{idx+1}/{len(subtasks)}]: {subtask}")
            # 子任务切换：重置停滞检测，防止 streak 跨子任务连续误判
            agent.reset_stuck()
            result = agent.run(subtask)
            result["subtask"] = subtask
            results.append(result)
            total_steps += result.get("steps", 0)
            self.history.append(f"[{idx+1}] {subtask} → {result.get('status')}")

            if result["status"] == "done":
                succeeded_indices.append(idx)
            else:
                print(f"  ⚠️ 子任务 {subtask} 未完成任务(status={result['status']})")
                if self.rollback_on_failure:
                    print("  🔄 触发回滚...")
                    self._rollback(succeeded_indices)
                    return {"status": "failed", "subtasks": idx + 1, "steps": total_steps,
                            "summary": f"子任务[{idx+1}]失败,已回滚", "failed_step": subtask}
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
            "你是移动端自动化任务规划师。把一个大任务拆解为有序的子任务,每个子任务是一个可独立执行的原子动作序列。\n"
            "格式：每行一个子任务，以编号开头（1. / 2. / 3. ...）。\n"
            "只输出子任务列表，不要解释、不要说明、不要额外文字。"
        )
        user = f"大任务：{task}\n要求：不超过{self.max_subtasks}个子任务，每个子任务要具体可执行（如\"点击搜索框\"、\"输入关键词\"）。"
        raw = self.llm.chat(system, user)
        steps = self._extract_steps(raw)
        return steps[:self.max_subtasks]

    @staticmethod
    def _extract_steps(raw: str) -> list[str]:
        """从 LLM 输出中提取子任务列表。

        只接受带编号标记的行（1. / 2) / • 第一步：/ ① 等）；
        无编号的兜底行会当作 LLM 的废话/解释而丢弃，避免被误执行。
        """
        steps: list[str] = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 剥离常见编号前缀
            stripped = TaskPlanner._strip_marker(line)
            if stripped is None:
                continue  # 非编号行，丢弃
            content = stripped.strip().lstrip(" \t")
            if content:
                steps.append(content)
            if len(steps) >= 10:
                break
        return steps

    @staticmethod
    def _strip_marker(line: str) -> str | None:
        """尝试剥离行首的编号标记，返回剩余内容；无法识别返回 None。

        支持：
        - 1. xxx / 1) xxx / 1)：xxx（数字 + 分隔符）
        - • 第一步：xxx / - 第二步 xxx（符号 + 第N步）
        - ① xxx / ②) xxx（圆圈数字）
        - • xxx / - xxx（符号行，仅当无其它强信号时也视作子任务）
        """
        # 中文数字（用 alt，避免字符类被当 range 解析异常）
        _CN = r"(?:一|二|两|三|四|五|六|七|八|九|十)"
        # 1) 符号 + "第N步"（N 可为阿拉伯或中文数字）
        m = re.match(r"^[\-•·.]+\s*第\s*(\d+|" + _CN + r")\s*步?\s*[.)：:]*\s*(.+)", line)
        if m:
            return m.group(2)
        # 1b) 符号 + "N步"（无"第"字）
        m = re.match(r"^[\-•·.]+\s*(\d+|" + _CN + r")\s*步?\s*[.)：:]*\s*(.+)", line)
        if m:
            return m.group(2)
        # 2) 数字/圆圈数字 + 分隔符（1. 2) ① ②)）
        m = re.match(r"^[\d①②③④⑤⑥⑦⑧⑨⑩][.)：:]\s*(.+)", line)
        if m:
            return m.group(1)
        # 2b) 圆圈数字 + 空格（① 打开 / ② 关闭）
        m = re.match(r"^[\d①②③④⑤⑥⑦⑧⑨⑩]\s+(.+)", line)
        if m:
            return m.group(1)
        # 3) 符号开头（• / - / . / ·）— 视作子任务标记
        if re.match(r"^[\-•·.]\s", line):
            return re.sub(r"^[\-•·.]\s*", "", line, count=1)
        return None

    def _rollback(self, succeeded_indices: list[int]) -> None:
        """回滚：按层级递减点击 back（比暴力多次 back 更可控，防退出 App）。

        对每个成功过的子任务各 back 一次，最多回滚成功子任务个数层。
        """
        print("  🔄 回滚中...")
        for _ in succeeded_indices:
            try:
                self.driver.execute_action({"action": "back"})
            except Exception:
                print("  ⚠️ 回滚中断（back 失败）")
                break
