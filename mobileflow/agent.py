"""Agent 主循环 —— 记忆回放 → 技能执行 → LLM 决策（含视觉通道/轨迹审计）。

决策链优先级：稳定记忆链 > 技能库 > LLM 在线决策 > 规划器。
轨迹审计：每步写 JSONL（未来对接 agent-tracer 可观测性）。
等待/重试：集成 wait_strategy 实现元素等待和动作重试。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.llm import LlmClient
from mobileflow.memory import MemoryEngine, MemoryIndex
from mobileflow.skills import SkillLibrary
from mobileflow.ui_tree import compress_page_source
from mobileflow.recoverer import SelfHealer
from mobileflow.vision import VisionChannel, format_vision_block


class Agent:
    def __init__(
        self,
        llm: LlmClient,
        driver: MobileDriver | DryDriver,
        max_steps: int = 20,
        settle_wait: float = 1.5,
        stuck_threshold: int = 3,
        memory: MemoryEngine | None = None,
        skills: SkillLibrary | None = None,
        vision: VisionChannel | None = None,
        healer: SelfHealer | None = None,
        trace_path: str | None = None,
    ) -> None:
        self.llm = llm
        self.driver = driver
        self.max_steps = max_steps
        self.settle_wait = settle_wait
        self.stuck_threshold = stuck_threshold
        self.memory = memory
        self.skills = skills
        self.vision = vision
        self.healer = healer
        self.trace_path = Path(trace_path) if trace_path else None
        self.history: list[str] = []
        self._last_ui_hash: str | None = None
        self._same_state_streak = 0

    # ---------- 主入口 ----------

    def run(self, task: str) -> dict[str, Any]:
        """执行任务：记忆 → 技能 → LLM 决策。"""
        print(f"🎯 任务: {task}")

        # 1. 稳定记忆链回放（精确 task_hash）
        if self.memory:
            chain = self.memory.lookup(task)
            if chain:
                print("🧠 记忆命中，回放动作链")
                if self._replay(task, chain):
                    return {"status": "done", "via": "memory", "steps": len(chain),
                            "summary": "记忆链回放成功"}
                print("↩️ 回放失败，回退在线决策")
                self.memory.record_failure(task)
            else:
                # 精确未命中 → RAG 语义检索相似稳定链
                ref = self._rag_recall(task)
                if ref and self._replay(task, ref["actions"]):
                    return {"status": "done", "via": "memory_rag", "steps": len(ref["actions"]),
                            "summary": f"记忆 RAG 命中相似任务「{ref['task']}」(sim={ref['similarity']})，回放成功"}
                if ref:
                    print(f"↩️ RAG 命中「{ref['task']}」(sim={ref['similarity']})但回放失败，回退在线决策")

        # 2. 技能库匹配
        if self.skills:
            skill = self.skills.match(task)
            if skill:
                print(f"📚 技能命中: {skill.get('name')}")
                steps = self.skills.render_steps(skill, {"app": task, "target": task})
                if self._replay(task, steps):
                    return {"status": "done", "via": "skill", "steps": len(steps),
                            "summary": f"技能「{skill.get('name')}」执行成功"}

        # 3. LLM 在线决策
        result = self._llm_loop(task)
        if result["status"] == "done" and self.memory:
            self.memory.record_success(task, result.get("actions", []))
        return result

    def _rag_recall(self, task: str) -> dict[str, Any] | None:
        """RAG 语义检索：从记忆库找最相似的稳定链，返回 top1 供参考。

        精确 task_hash 未命中时才走这里；相似度最高的相似任务动作链可作为
        参考回放（而非强行套用）。无记忆库或无索引返回 None。
        """
        if not self.memory:
            return None
        try:
            index = MemoryIndex(self.memory)
        except Exception:
            return None
        results = index.search(task, top_k=1, threshold=0.18)
        if not results:
            return None
        return results[0]

    # ---------- 记忆/技能回放 ----------

    def _replay(self, task: str, actions: list[dict[str, Any]]) -> bool:
        """回放动作序列，UI 无变化即判失败。"""
        for i, action in enumerate(actions, 1):
            ui_before = self._ui_hash()
            try:
                result = self.driver.execute_action(action)
            except Exception as e:
                print(f"  ⚠️ 回放第 {i} 步失败: {e}")
                return False
            print(f"  [{i}/{len(actions)}] {action.get('action')}: {result}")
            self._trace(task, "replay", action, result)
            time.sleep(self.settle_wait)
            if self._ui_hash() == ui_before and action.get("action") not in ("done", "back", "home"):
                print(f"  ⚠️ 第 {i} 步后 UI 无变化，回放中止")
                return False
        return True

    # ---------- LLM 在线决策循环 ----------

    def _llm_loop(self, task: str) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            ui_text = compress_page_source(self.driver.page_source())
            print(f"\n—— 第 {step} 步 ——")

            if self._check_stuck(ui_text):
                return {"status": "stuck", "steps": step,
                        "summary": f"UI 连续 {self.stuck_threshold} 步无变化，判定停滞"}

            # 视觉通道（可选）：截图描述补充 UI 树
            vision_block = ""
            if self.vision and hasattr(self.driver, "screenshot_b64") and callable(getattr(self.driver, "screenshot_b64", None)):
                b64 = self.driver.screenshot_b64()
                if b64:
                    try:
                        desc = self.vision.describe_screenshot(b64)
                        vision_block = format_vision_block(desc)
                        print(f"👁️ 视觉: {desc[:80]}...")
                    except Exception as e:
                        print(f"  ⚠️ 视觉通道失败: {e}")

            action = self.llm.decide_action(ui_text + vision_block, task, self.history)
            if not isinstance(action, dict) or not action.get("action"):
                raise ValueError(f"LLM 返回非法动作: {action!r}")

            try:
                result = self.driver.execute_action(action)
                recovered = False
            except Exception as e:
                # 执行失败 → 自愈：视觉 + LLM 分析失败并重规划
                recovered = True
                result = self._recover_and_retry(task, action, e, ui_text, vision_block)

            print(f"决策: {action}")
            print(f"执行: {result}")
            self.history.append(f"{action.get('action')}: {result}" + (" [自愈]" if recovered else ""))
            self._trace(task, "llm", action, result)
            actions.append(action)

            if action.get("action") == "done":
                return {"status": "done", "steps": step, "actions": actions,
                        "summary": action.get("summary", "")}

            time.sleep(self.settle_wait)

        return {"status": "timeout", "steps": self.max_steps, "actions": actions,
                "summary": "达到最大步数"}

    # ---------- 自愈 ----------

    def _recover_and_retry(
        self,
        task: str,
        failed_action: dict[str, Any],
        error: Exception,
        ui_text: str,
        vision_block: str,
    ) -> str:
        """执行失败 → 自愈重规划 → 重试验证。"""
        if not self.healer:
            return f"⚠️ 执行失败且无恢复器: {error}"
        print(f"  🩹 动作失败({error})，触发自愈重规划...")
        # 截屏给恢复器（可选）
        b64 = None
        if hasattr(self.driver, "screenshot_b64") and callable(getattr(self.driver, "screenshot_b64", None)):
            try:
                b64 = self.driver.screenshot_b64()
            except Exception:
                b64 = None
        try:
            recover_action = self.healer.recover(
                ui_text=ui_text,
                screenshot_b64=b64,
                failed_action=failed_action,
                error=error,
                task=task,
                history=self.history,
            )
        except Exception as e:
            return f"⚠️ 恢复器分析失败: {e}"
        if recover_action is None:
            return f"⚠️ 执行失败且无法恢复: {error}"
        rec = recover_action.get("action", "?")
        print(f"  🩹 恢复动作: {rec} {recover_action}")
        try:
            rec_result = self.driver.execute_action(recover_action)
        except Exception as e:
            return f"⚠️ 恢复动作也失败({rec}): {e}"
        # 给 UI 一个稳定时间后重试原动作
        time.sleep(self.settle_wait)
        try:
            retry_result = self.driver.execute_action(failed_action)
            return f"{rec_result}; 重试原动作成功: {retry_result}"
        except Exception as e:
            return f"{rec_result}; 重试原动作仍失败: {e}"

    # ---------- 工具 ----------

    def _ui_hash(self) -> str:
        return hashlib.md5(self.driver.page_source().encode()).hexdigest()

    def reset_stuck(self) -> None:
        """重置停滞检测状态。子任务切换时调用，防止 streak 跨子任务连续误判。"""
        self._same_state_streak = 0
        self._last_ui_hash = None

    def _check_stuck(self, ui_text: str) -> bool:
        ui_hash = hashlib.md5(ui_text.encode()).hexdigest()
        if ui_hash == self._last_ui_hash:
            self._same_state_streak += 1
        else:
            self._same_state_streak = 0
            self._last_ui_hash = ui_hash
        return self._same_state_streak >= self.stuck_threshold

    def _trace(self, task: str, via: str, action: dict[str, Any], result: str) -> None:
        """轨迹审计：JSONL 追加（可观测性）。"""
        if not self.trace_path:
            return
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(), "task": task, "via": via,
                "action": action, "result": result,
            }, ensure_ascii=False) + "\n")
