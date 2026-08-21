"""CLI 入口：mobileflow run "任务" [--dry-run] [--vision] | skills list/add | memory stats"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mobileflow.agent import Agent
from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.llm import LlmClient
from mobileflow.memory import MemoryEngine
from mobileflow.planner import TaskPlanner
from mobileflow.skills import SkillLibrary
from mobileflow.vision import VisionChannel


SAMPLE_UI = """<node resource-id="com.example:id/list" bounds="[0,100][1080,2200]">
  <node text="微信" resource-id="com.example:id/app_name" clickable="true" bounds="[0,300][360,500]"/>
  <node text="支付宝" resource-id="com.example:id/app_name" clickable="true" bounds="[0,520][360,720]"/>
  <node text="设置" resource-id="com.example:id/app_name" clickable="true" bounds="[0,740][360,940]"/>
</node>"""


def build_driver(dry_run: bool, appium_url: str, capabilities: str) -> MobileDriver | DryDriver:
    if dry_run:
        return DryDriver(SAMPLE_UI)
    from appium import webdriver
    caps = json.loads(capabilities) if capabilities != "{}" else {
        "platformName": "Android",
        "automationName": "UiAutomator2",
        "appPackage": "com.android.settings",
        "appActivity": ".Settings",
    }
    return MobileDriver(webdriver.Remote(appium_url, caps))


def cmd_run(args: argparse.Namespace) -> None:
    # 启动即校验配置，失败立即退出，不消耗 LLM token
    try:
        from mobileflow.config import validate_all, ConfigError
        validate_all(vision_enabled=bool(args.vision and not args.dry_run), strict_key=True)
    except ConfigError as e:
        print(f"❌ {e}")
        sys.exit(2)

    print("⚠️ dry-run 模式：无真实设备，使用示例 UI 树" if args.dry_run else "")
    driver = build_driver(args.dry_run, args.appium_url, args.capabilities)
    llm = LlmClient()

    try:
        _cmd_run_impl(args, driver, llm)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断 (Ctrl+C)，任务已停止")
        sys.exit(130)


def _cmd_run_impl(args: argparse.Namespace, driver, llm) -> None:

    agent = None  # 先置空，避免 --plan 分支后访问未定义
    # 有 planner 时用规划器，否则用普通 Agent
    if args.plan:
        planner = TaskPlanner(
            llm, driver,
            max_steps_per_subtask=args.max_steps,
            max_subtasks=args.max_subtasks,
            trace_path=args.trace,
        )
        result = planner.run(args.task)
    else:
        agent = Agent(
            llm, driver,
            max_steps=args.max_steps,
            memory=MemoryEngine() if not args.no_memory else None,
            skills=SkillLibrary() if not args.no_skills else None,
            vision=VisionChannel() if args.vision and not args.dry_run else None,
            trace_path=args.trace,
        )
        result = agent.run(args.task)

    print("\n📋 结果:", json.dumps(result, ensure_ascii=False, indent=1))
    if args.dry_run and not args.plan:
        print("\n🧾 决策轨迹:")
        for i, h in enumerate(agent.history, 1):
            print(f"  {i}. {h}")
    if not args.plan and hasattr(agent, 'memory') and agent.memory:
        print("\n🧠 记忆:", json.dumps(agent.memory.stats(), ensure_ascii=False, indent=1))

    # 报告产出（可选）
    if args.report:
        from mobileflow.report import ReportBuilder
        rb = ReportBuilder(suite_name="mobileflow")
        rb.add_case(name=args.task, result=result, trace_path=args.trace)
        report_dir = Path(args.report)
        rb.write_json(report_dir / "summary.json")
        rb.write_allure(report_dir / "allure")
        s = rb.summary()
        print(
            f"\n📊 报告已生成: {report_dir.resolve()} "
            f"(通过 {s['passed']}/{s['total']}, 报告目录含 summary.json + allure/)"
        )


def cmd_skills(args: argparse.Namespace) -> None:
    lib = SkillLibrary()
    if args.action == "list":
        for name in lib.list():
            skill = lib.skills[name]
            print(f"- {name}: {skill.get('description', '')}")
    elif args.action == "add":
        import yaml
        skill = yaml.safe_load(open(args.file, encoding="utf-8"))
        lib.add(skill)
        print(f"✅ 技能已添加: {skill.get('name')}")


def cmd_memory(args: argparse.Namespace) -> None:
    mem = MemoryEngine()
    print(json.dumps(mem.stats(), ensure_ascii=False, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(prog="mobileflow", description="LLM 驱动移动端自动化")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="执行自然语言任务")
    run.add_argument("task", help='任务描述，如 "打开微信发消息"')
    run.add_argument("--dry-run", action="store_true", help="无设备，只验证 LLM 决策链路")
    run.add_argument("--appium-url", default="http://127.0.0.1:4723", help="Appium 服务地址")
    run.add_argument("--max-steps", type=int, default=20, help="每个子任务最大步数")
    run.add_argument("--max-subtasks", type=int, default=5, help="任务拆解最大子任务数")
    run.add_argument("--vision", action="store_true", help="开启截图多模态通道")
    run.add_argument("--no-memory", action="store_true", help="关闭记忆链")
    run.add_argument("--no-skills", action="store_true", help="关闭技能库")
    run.add_argument("--trace", default=None, help="轨迹审计输出路径（JSONL）")
    run.add_argument("--capabilities", default="{}", help='JSON 字符串，Android desired capabilities')
    run.add_argument("--plan", action="store_true", help="启用任务规划器（拆解大任务为子任务链）")
    run.add_argument("--report", default=None, help="报告输出目录（生成 summary.json + allure/ 兼容 Allure 审计报告）")
    run.set_defaults(func=cmd_run)

    skills = sub.add_parser("skills", help="技能库管理")
    skills.add_argument("action", choices=["list", "add"])
    skills.add_argument("--file", help="技能 YAML 文件（add 时）")
    skills.set_defaults(func=cmd_skills)

    mem = sub.add_parser("memory", help="记忆统计")
    mem.set_defaults(func=cmd_memory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
