import json
import os

from mobileflow.memory import MemoryEngine, task_hash


def test_task_hash_case_insensitive():
    assert task_hash("A  B") == task_hash("a b")


def test_lookup_new_chain_hits_one_returns_none(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.json")
    result = engine.lookup("some task")
    assert result is None


def test_record_success_twice_lookup_returns_latest_actions(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.json")
    task = "do something"
    engine.record_success(task, ["action1", "action2"])
    engine.record_success(task, ["actionA", "actionB"])

    result = engine.lookup(task)
    assert result == ["actionA", "actionB"]


def test_record_failure_twice_after_stable_chain_deletes_it(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.json")
    task = "failing task"
    engine.record_success(task, ["a1"])
    engine.record_success(task, ["a2"])
    assert engine.lookup(task) is not None

    engine.record_failure(task)
    engine.record_failure(task)
    assert engine.lookup(task) is None


def test_stats_counts_chains_and_stable(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.json")
    engine.record_success("task1", ["a"])
    engine.record_success("task1", ["b"])
    engine.record_success("task2", ["c"])

    stats = engine.stats()
    assert stats["chains"] == 2
    assert stats["stable"] == 1


def test_memory_engine_persists_json_to_disk(tmp_path):
    db_path = tmp_path / "memory.json"
    engine = MemoryEngine(db_path)
    engine.record_success("persisted task", ["step1", "step2"])
    engine.record_success("persisted task", ["step3", "step4"])

    assert os.path.exists(db_path)
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "chains" in data
    chains = data["chains"]
    h = task_hash("persisted task")
    assert h in chains
    entry = chains[h]
    assert set(entry.keys()) >= {"task", "hits", "actions"}
    assert entry["task"] == "persisted task"
    assert entry["hits"] == 2
    assert entry["actions"] == ["step3", "step4"]


# -------------------- RAG 语义检索 --------------------

from mobileflow.memory import MemoryIndex


def _mk_engine_with_stable_chains(tmp_path):
    """造一个含 4 条稳定链（hits>=2）的记忆引擎供 RAG 测试。"""
    from mobileflow.memory import MemoryEngine
    eng = MemoryEngine(tmp_path / "mem.json")
    tasks = {
        "打开微信发送消息": [{"action": "open_app", "package": "wx"}, {"action": "done"}],
        "点击搜索框输入关键词": [{"action": "click", "target": {"text": "搜索"}}, {"action": "done"}],
        "关闭应用回到桌面": [{"action": "home"}, {"action": "done"}],
        "进入设置开启WiFi": [{"action": "click", "target": {"text": "设置"}}, {"action": "done"}],
    }
    for t, acts in tasks.items():
        eng.record_success(t, acts)
        eng.record_success(t, acts)  # hits=2 升稳定链
    return eng


def test_rag_search_returns_similar_task(tmp_path):
    eng = _mk_engine_with_stable_chains(tmp_path)
    idx = MemoryIndex(eng)
    results = idx.search("给好友发一条微信消息", top_k=2)
    assert results, "应检索到相似任务"
    best = results[0]
    assert "微信" in best["task"] or "发送消息" in best["task"]
    assert best["similarity"] >= 0.18
    assert best["actions"][0]["action"] == "open_app"


def test_rag_ranks_by_similarity(tmp_path):
    eng = _mk_engine_with_stable_chains(tmp_path)
    idx = MemoryIndex(eng)
    results = idx.search("搜索并输入关键词", top_k=3)
    assert results
    # 最相关的应是搜索框那条
    assert "搜索" in results[0]["task"]
    sims = [r["similarity"] for r in results]
    assert sims == sorted(sims, reverse=True)


def test_rag_threshold_filters_weak_matches(tmp_path):
    eng = _mk_engine_with_stable_chains(tmp_path)
    idx = MemoryIndex(eng)
    # 高阈值几乎无匹配
    results = idx.search("完全无关的任务xyz", top_k=5, threshold=0.9)
    assert results == []


def test_rag_empty_index_returns_empty(tmp_path):
    from mobileflow.memory import MemoryEngine
    eng = MemoryEngine(tmp_path / "empty.json")
    idx = MemoryIndex(eng)
    assert idx.search("任意任务") == []
