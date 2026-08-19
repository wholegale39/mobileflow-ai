"""CLI 入口：mobileflow run "任务" [--dry-run] [--appium-url ...]"""
from __future__ import annotations

import argparse
import json
import sys

from mobileflow.agent import Agent
from mobileflow.driver import DryDriver, MobileDriver
from mobileflow.llm import LlmClient


SAMPLE_UI = """<node resource-id="com.example:id/list" bounds="[0,100][1080,2200]">
  <node text="微信" resource-id="com.example:id/app_name" clickable="true" bounds="[0,300][360,500]"/>
  <node text="支付宝" resource-id="com.example:id/app_name" clickable="true" bounds="[0,520][360,720]"/>
  <node text="设置" resource-id="com.example:id/app_name" clickable="true" bounds="[0,740][360,940]"/>
</node>"""


def main() -> None:
    parser = argparse.ArgumentParser(prog="mobileflow", description="LLM 驱动移动端自动化")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="执行自然语言任务")
    run.add_argument("task", help='任务描述，如 "打开微信发消息"')
    run.add_argument("--dry-run", action="store_true", help="无设备，只验证 LLM 决策链路")
    run.add_argument("--appium-url", default="http://127.0.0.1:4723", help="Appium 服务地址")
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument("--capabilities", default="{}", help='JSON 字符串，Android desired capabilities')

    args = parser.parse_args()

    llm = LlmClient()

    if args.dry_run:
        driver: DryDriver = DryDriver(SAMPLE_UI)
        print("⚠️ dry-run 模式：无真实设备，使用示例 UI 树")
    else:
        from appium import webdriver
        caps = json.loads(args.capabilities) if args.capabilities != "{}" else {
            "platformName": "Android",
            "automationName": "UiAutomator2",
            "appPackage": "com.android.settings",
            "appActivity": ".Settings",
        }
        wd = webdriver.Remote(args.appium_url, caps)
        driver = MobileDriver(wd)

    agent = Agent(llm, driver, max_steps=args.max_steps)
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


if __name__ == "__main__":
    main()
