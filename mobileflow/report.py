"""测试报告 —— 结构化运行结果 + Allure 兼容格式。

把单次/批量 mobileflow 运行的结果聚合成可被 CI 消费的测试报告：
- summary.json: 机器可读的汇总（用例数、通过率、各用例状态/步骤/耗时/决策链路）
- allure/ 目录: 兼容 Allure 的 results 目录（container.json + execution_data），
  用 allure generate 即可渲染成可视化审计报告，含 LLM 决策日志。

零新依赖：Allure 格式本质是 JSON，无需在本工程安装 allure CLI（外部 CI 渲染）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ReportBuilder:
    """聚合运行结果为结构化测试报告。"""

    def __init__(self, suite_name: str = "mobileflow") -> None:
        self.suite = suite_name
        self._cases: list[dict[str, Any]] = []
        self._started_at: float | None = None

    def add_case(
        self,
        *,
        name: str,
        result: dict[str, Any],
        trace_path: str | None = None,
        duration: float | None = None,
    ) -> None:
        """登记一个用例（对应一次 agent.run）。

        Args:
            name: 用例/任务名称。
            result: agent.run 返回的 dict（status/via/steps/summary/actions）。
            trace_path: 可选，该用例的轨迹 JSONL 路径，会被读入报告作为决策链路。
            duration: 可选，该用例耗时秒数。
        """
        if self._started_at is None:
            self._started_at = time.time()
        status = result.get("status")
        # status -> 用例结论映射
        if status == "done":
            conclusion = "passed"
        elif status in ("stuck", "failed"):
            conclusion = "failed"
        else:  # timeout / None
            conclusion = "broken" if status == "timeout" else "unknown"

        # 读入轨迹作为决策链路（可选）
        decisions: list[dict[str, Any]] = []
        if trace_path:
            decisions = self._load_trace(trace_path)

        self._cases.append({
            "name": name,
            "conclusion": conclusion,
            "status": status,
            "via": result.get("via"),
            "steps": result.get("steps", 0),
            "summary": result.get("summary", ""),
            "duration": duration,
            "decisions": decisions,
        })

    def write_json(self, path: str | Path) -> Path:
        """写出结构化汇总报告（summary.json）。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        report = self._build_report()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_allure(self, out_dir: str | Path) -> Path:
        """写出 Allure 兼容 results 目录（含 suite + 每用例 execution_data）。

        用 `allure generate <out_dir>` 可渲染成可视化审计报告。
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        suite_container = self._suite_container()
        (out_dir / "container.json").write_text(
            json.dumps(suite_container, ensure_ascii=False), encoding="utf-8"
        )
        for i, case in enumerate(self._cases):
            data = self._case_execution_data(case, i)
            (out_dir / f"test_{i}.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        return out_dir

    def summary(self) -> dict[str, Any]:
        """返回内存中的汇总（不写文件）。"""
        return self._build_report()

    # ---------- 内部 ----------

    def _build_report(self) -> dict[str, Any]:
        total = len(self._cases)
        passed = sum(1 for c in self._cases if c["conclusion"] == "passed")
        return {
            "suite": self.suite,
            "total": total,
            "passed": passed,
            "failed": sum(1 for c in self._cases if c["conclusion"] == "failed"),
            "broken": sum(1 for c in self._cases if c["conclusion"] == "broken"),
            "pass_rate": round(passed / total, 3) if total else 0.0,
            "cases": self._cases,
        }

    @staticmethod
    def _load_trace(path: str) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        try:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        decisions.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return decisions

    def _suite_container(self) -> dict[str, Any]:
        return {
            "uuid": "mobileflow-suite",
            "name": self.suite,
            "children": list(range(len(self._cases))),
            "befores": [],
            "afters": [],
        }

    def _case_execution_data(self, case: dict[str, Any], idx: int) -> dict[str, Any]:
        history: list[dict[str, Any]] = []
        for d in case.get("decisions", []):
            history.append({
                "timestamp": int(d.get("ts", 0) * 1000) if d.get("ts") else 0,
                "duration": 0,
                "stage": "step",
                "status": "passed",
                "name": f"{d.get('via', '?')} {d.get('action', {}).get('action', '?')}",
                "historyItem": {
                    "title": str(d.get("action", {})),
                    "description": str(d.get("result", "")),
                },
            })
        return {
            "uuid": f"mobileflow-test-{idx}",
            "name": case["name"],
            "status": case["conclusion"],
            "stage": "finished",
            "duration": int((case.get("duration") or 0) * 1000),
            "historyItems": [
                {
                    "title": "执行方式",
                    "description": f"via={case.get('via')} steps={case.get('steps')} summary={case.get('summary')}",
                }
            ],
            "history": history,
        }
