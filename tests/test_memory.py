import json
import os
import pytest

from mobileflow.memory import task_hash, MemoryEngine


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
