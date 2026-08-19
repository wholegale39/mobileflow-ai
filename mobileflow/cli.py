"""CLI 入口：mobileflow run "任务" [--dry-run] [--vision] | skills list/add | memory stats"""
from __future__ import annotations

import argparse
import json
import sys

from mobileflow.agent import Agent
from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.llm import LlmClient
from mobileflow.memory import MemoryEngine
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
    print("⚠️ dry-run 模式：无真实设备，使用示例 UI 树" if args.dry_run else "")
    driver = build_driver(args.dry_run, args.appium_url, args.capabilities)
    llm = LlmClient()
    agent = Agent(
        llm, driver,
        max_steps=args.max_steps,
        memory=MemoryEngine() if not args.no_memory else None,
        skills=SkillLibrary() if not args.no_skills else None,
        vision=VisionChannel() if args.vision and not args.dry_run else None,
        trace_path=args.trace,
    )
    try:
        result = agent.run(args.task)
    except KeyboardInterrupt:
        print("\n🛑 已中断")
        sys.exit(130)

    print("\n📋 结果:", json.dumps(result, ensure_ascii=False))
    if args.dry_run:
        print("\n🧾 决策轨迹:")
        for i, h in enumerate(agent.history, 1):
            print(f"  {i}. {h}")
    if agent.memory:
        print("\n🧠 记忆:", json.dumps(agent.memory.stats(), ensure_ascii=False))


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
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument("--vision", action="store_true", help="开启截图多模态通道")
    run.add_argument("--no-memory", action="store_true", help="关闭记忆链")
    run.add_argument("--no-skills", action="store_true", help="关闭技能库")
    run.add_argument("--trace", default=None, help="轨迹审计输出路径（JSONL）")
    run.add_argument("--capabilities", default="{}", help='JSON 字符串，Android desired capabilities')
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
