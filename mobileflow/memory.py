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


# =========================================================================
# RAG 语义检索层 —— 基于记忆链的字符 n-gram + 余弦相似度，零新依赖
# =========================================================================

import numpy as np


def _ngrams(text: str, n: int = 2) -> set[str]:
    """字符 n-gram（对中文天然有效，无需分词）。"""
    return {text[i : i + n] for i in range(len(text) - n + 1)}


class MemoryIndex:
    """记忆库的语义检索索引。

    当精确 task_hash 未命中时，用 RAG 检索最相似的历史任务，
    返回相似任务及其动作链，供 Agent 参考（而非直接回放）。

    基于字符 n-gram + TF-IDF 权重 + 余弦相似度，纯 numpy 实现，
    无需下载任何 embedding 模型，离线可用、轻量。
    """

    def __init__(self, mem: MemoryEngine, *, ngram_n: int = 2) -> None:
        self.mem = mem
        self.n = ngram_n
        self._vocab: list[str] = []
        self._df: dict[str, int] = {}
        self._vectors: np.ndarray | None = None  # 每行一个稳定链，TF-IDF 加权
        self._tasks: list[str] = []
        self._dirty = True
        self._rebuild()

    def _rebuild(self) -> None:
        """根据当前稳定链重建索引。"""
        chains = self.mem.data.get("chains", {})
        tasks = [c["task"] for c in chains.values() if c.get("hits", 0) >= 2]
        # 建词汇表 + 文档频率
        vocab: dict[str, int] = {}
        df: dict[str, int] = {}
        for t in tasks:
            for g in _ngrams(t, self.n):
                vocab.setdefault(g, 0)
                df[g] = df.get(g, 0) + 1
        vocab_list = sorted(vocab)
        V = len(vocab_list)
        idx = {g: i for i, g in enumerate(vocab_list)}
        N = len(tasks)
        if N == 0:
            self._vectors = None
            self._tasks = []
            self._vocab = vocab_list
            self._df = df
            return
        arr = np.zeros((N, V))
        for row, t in enumerate(tasks):
            for g in _ngrams(t, self.n):
                if g in idx:
                    # IDF 权重（拉普拉斯平滑）
                    arr[row, idx[g]] = np.log((N + 1) / (df.get(g, 0) + 1)) + 1.0
        # L2 归一化（余弦相似度 = 点积）
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = np.where(norms > 0, arr / norms, 0.0)
        self._vectors = arr
        self._tasks = tasks
        self._vocab = vocab_list
        self._df = df

    def search(self, task: str, top_k: int = 3, threshold: float = 0.18) -> list[dict[str, Any]]:
        """检索与 task 语义最相似的稳定链。

        Returns:
            [{"task": "...", "similarity": 0.6, "actions": [...], "hits": 2}, ...]
            按相似度降序，仅返回 >= threshold 的结果。无索引或无匹配返回空列表。
        """
        if self._vectors is None or len(self._tasks) == 0:
            return []
        vecs = self._vectors
        if vecs is None:
            return []
        q = np.zeros(len(self._vocab))
        for g in _ngrams(task, self.n):
            if g in self._vocab:
                i = self._vocab.index(g)
                q[i] = np.log((len(self._tasks) + 1) / (self._df.get(g, 0) + 1)) + 1.0
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        q = q / qn
        sims = vecs @ q
        chains = self.mem.data.get("chains", {})
        results: list[dict[str, Any]] = []
        for i, score in enumerate(np.argsort(-sims)):
            s = float(sims[score])
            if s < threshold:
                break
            t = self._tasks[score]
            h = task_hash(t)
            c = chains.get(h, {})
            results.append({
                "task": t,
                "similarity": round(s, 3),
                "actions": c.get("actions", []),
                "hits": c.get("hits", 0),
            })
            if len(results) >= top_k:
                break
        return results
