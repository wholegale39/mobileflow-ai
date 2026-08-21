"""测试 cli 入口：参数解析、报告产出、配置校验拦截。"""
from __future__ import annotations

import json
import io
import contextlib

from mobileflow import cli as cli_mod


def _run(argv, monkeypatch, fake_llm=False):
    """模拟 sys.argv 调用 main, 返回 (stdout, exit_code)。
    fake_llm=True 时让 LlmClient.decide_action 立即返回 done, 避免真实 LLM 调用。
    """
    monkeypatch.setattr(cli_mod.sys, "argv", ["mobileflow"] + argv)
    if fake_llm:
        def _fake_decide(self, *a, **kw):
            return {"action": "done"}
        monkeypatch.setattr(cli_mod.LlmClient, "decide_action", _fake_decide)
    buf = io.StringIO()
    rc = 0
    with contextlib.redirect_stdout(buf):
        try:
            cli_mod.main()
        except SystemExit as e:
            rc = int(e.code or 0)
    return buf.getvalue(), rc


def test_cli_run_report_produces_files(tmp_path, monkeypatch):
    """--report 应产出 summary.json + allure/ 目录。"""
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-testdummy123")
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    report = tmp_path / "rpt"
    out, rc = _run([
        "run", "打开微信", "--dry-run", "--no-memory", "--no-skills",
        "--report", str(report),
    ], monkeypatch, fake_llm=True)
    assert rc == 0
    assert (report / "summary.json").exists(), "summary.json 应生成"
    assert (report / "allure" / "container.json").exists(), "allure/container.json 应生成"
    s = json.loads((report / "summary.json").read_text(encoding="utf-8"))
    assert s["suite"] == "mobileflow"
    assert "报告已生成" in out


def test_cli_run_no_report_no_files(monkeypatch):
    """未传 --report 不产出报告提示。"""
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-testdummy123")
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    out, rc = _run(
        ["run", "打开微信", "--dry-run", "--no-memory", "--no-skills"],
        monkeypatch, fake_llm=True,
    )
    assert rc == 0
    assert "报告已生成" not in out


def test_cli_run_config_fail_exits2(monkeypatch):
    """配置校验失败应 exit 2, 且提示中文错误。"""
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "dummybadkey")
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    out, rc = _run(["run", "x", "--dry-run", "--no-memory", "--no-skills"], monkeypatch)
    assert rc == 2
    assert "配置校验失败" in out


def test_cli_skills_list(monkeypatch):
    out, rc = _run(["skills", "list"], monkeypatch)
    assert rc == 0
    assert "open_app" in out and "打开指定应用" in out
