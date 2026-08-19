"""记忆链 —— 任务级动作序列复用。

AppAgentX 风格：相同任务（语义哈希）成功执行后缓存动作序列；
再次遇到直接回放，失败回退 LLM 决策。重复成功 ≥2 次提升为稳定链。
存储：JSON 文件（默认 ~/.mobileflow/memory.json），原子写防损坏。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def task_hash(task: str) -> str:
    """任务语义哈希（归一化：去空格/大小写）。"""
    norm = " ".join(task.lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


class MemoryEngine:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.environ.get("MOBILEFLOW_MEMORY", "~/.mobileflow/memory.json")).expanduser()
        self.data: dict[str, Any] = {"chains": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            # 损坏不静默清空：备份后重建，避免丢历史记忆
            backup = self.path.with_suffix(f".corrupt-{int(time.time())}.json")
            try:
                self.path.replace(backup)
                print(f"⚠️ memory.json 损坏，已备份到 {backup.name}，重建空记忆")
            except OSError:
                pass
            self.data = {"chains": {}}

    def _save(self) -> None:
        """原子写：tmp + rename，防止写一半崩溃损坏文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def lookup(self, task: str) -> list[dict[str, Any]] | None:
        """命中稳定链（hits>=2）返回动作序列，否则 None。

        首次成功 hits=1 属"实验链"，不回放；再次成功升为稳定链才回放。
        """
        h = task_hash(task)
        chain = self.data["chains"].get(h)
        if chain and chain.get("hits", 0) >= 2:
            return chain.get("actions", [])
        return None

    def record_success(self, task: str, actions: list[dict[str, Any]]) -> None:
        """记录一次成功执行，命中+1，用最新成功序列。"""
        h = task_hash(task)
        chain = self.data["chains"].get(h)
        if chain:
            chain["hits"] += 1
            chain["actions"] = actions
        else:
            self.data["chains"][h] = {"task": task, "hits": 1, "actions": actions}
        self._save()

    def record_failure(self, task: str) -> None:
        """回放失败：命中-1，低于 1 删除。"""
        h = task_hash(task)
        chain = self.data["chains"].get(h)
        if chain:
            chain["hits"] -= 1
            if chain["hits"] < 1:
                del self.data["chains"][h]
            self._save()

    def stats(self) -> dict[str, Any]:
        chains = self.data.get("chains", {})
        return {
            "chains": len(chains),
            "stable": sum(1 for c in chains.values() if c.get("hits", 0) >= 2),
        }
