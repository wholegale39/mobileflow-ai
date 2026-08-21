"""测试 report 报告模块：汇总报告 + Allure 兼容格式。"""
from __future__ import annotations

import json
from pathlib import Path

from mobileflow.report import ReportBuilder


def test_summary_json_single_passed(tmp_path):
    rb = ReportBuilder(suite_name="suite1")
    rb.add_case(name="打开微信", result={"status": "done", "via": "llm", "steps": 3, "summary": "ok"})
    p = rb.write_json(tmp_path / "summary.json")
    report = json.loads(p.read_text(encoding="utf-8"))
    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["pass_rate"] == 1.0
    assert report["cases"][0]["conclusion"] == "passed"


def test_summary_json_batch(tmp_path):
    rb = ReportBuilder()
    rb.add_case(name="t1", result={"status": "done", "steps": 2})
    rb.add_case(name="t2", result={"status": "failed", "steps": 1})
    rb.add_case(name="t3", result={"status": "timeout", "steps": 5})
    report = rb.write_json(tmp_path / "r.json")
    d = json.loads(report.read_text(encoding="utf-8"))
    assert d["total"] == 3
    assert d["passed"] == 1
    assert d["failed"] == 1
    assert d["broken"] == 1
    cases = {c["name"]: c["conclusion"] for c in d["cases"]}
    assert cases["t1"] == "passed"
    assert cases["t2"] == "failed"
    assert cases["t3"] == "broken"


def test_allure_dir_structure(tmp_path):
    rb = ReportBuilder(suite_name="mysuite")
    rb.add_case(name="用例A", result={"status": "done", "via": "memory", "steps": 2, "summary": "记忆命中"})
    rb.add_case(name="用例B", result={"status": "stuck", "steps": 3})
    rd = rb.write_allure(tmp_path / "report" / "allure")
    assert (rd / "container.json").exists()
    assert (rd / "test_0.json").exists()
    assert (rd / "test_1.json").exists()
    container = json.loads((rd / "container.json").read_text(encoding="utf-8"))
    assert container["name"] == "mysuite"
    assert len(container["children"]) == 2
    t0 = json.loads((rd / "test_0.json").read_text(encoding="utf-8"))
    assert t0["name"] == "用例A"
    assert t0["status"] == "passed"
    t1 = json.loads((rd / "test_1.json").read_text(encoding="utf-8"))
    assert t1["status"] == "failed"
    # 执行方式 description 含 via/steps
    desc = t0["historyItems"][0]["description"]
    assert "memory" in desc and "steps=2" in desc


def test_allure_includes_trace_decisions(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        '{"ts":1.0,"task":"t","via":"llm","action":{"action":"click"},"result":"ok"}\n'
        '{"ts":2.0,"task":"t","via":"llm","action":{"action":"done"},"result":"done"}\n',
        encoding="utf-8",
    )
    rb = ReportBuilder()
    rb.add_case(name="带轨迹", result={"status": "done", "steps": 2}, trace_path=str(trace))
    rd = rb.write_allure(tmp_path / "a")
    t = json.loads((rd / "test_0.json").read_text(encoding="utf-8"))
    assert len(t["history"]) == 2
    assert t["history"][0]["historyItem"]["title"] == "{'action': 'click'}"


def test_trace_missing_does_not_crash(tmp_path):
    rb = ReportBuilder()
    rb.add_case(name="无轨迹", result={"status": "done"}, trace_path=str(tmp_path / "nope.jsonl"))
    report = rb.summary()
    assert report["cases"][0]["decisions"] == []
