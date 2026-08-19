#!/usr/bin/env python3
"""交叉评审器 —— agnes-2.5-pro 评审代码，作为 GLM-5.2 生成的质量闸门。

用法:
    python3 tools/review_code.py mobileflow/llm.py [mobileflow/driver.py ...]
    python3 tools/review_code.py --all          # 评审整个包
    python3 tools/review_code.py --gate         # 有 🔴 严重问题则 exit 1（CI 用）

评审流: GLM-5.2 生成 → agnes-2.5-pro 评审 → 人工/agent 修复 → 复评
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-2.5-pro"


def read_env() -> dict[str, str]:
    env = {}
    with open("/opt/data/.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def stream_chat(system: str, user: str, max_tokens: int = 4000) -> str:
    """流式调用 agnes-2.5-pro（直出模式，stream 避免长响应断连）。"""
    env = read_env()
    key = env.get("AGNES_API_KEY", "")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "reasoning_effort": "none",  # pro 思考模式长响应会断连，直出才稳
        "max_tokens": max_tokens,
        "stream": True,
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    t0 = time.time()
    parts: list[str] = []
    try:
        resp = urllib.request.urlopen(req, timeout=180)  # 直连（已实测可用）
        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        break
                    try:
                        d = json.loads(data)
                        delta = d["choices"][0].get("delta", {})
                        if delta.get("content"):
                            parts.append(delta["content"])
                    except Exception:
                        pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")
    full = "".join(parts)
    print(f"  （agnes-2.5-pro 评审 {time.time()-t0:.1f}s / {len(full)} 字符）")
    return full


REVIEW_SYSTEM = (
    "你是资深 Python 代码评审官，负责交叉评审另一个 AI 生成的代码。"
    "按以下格式输出评审意见（中文）：\n"
    "🔴 严重问题（bug/安全/逻辑错误，必须修复）\n- 文件:行号 问题描述\n"
    "🟡 改进点（可读性/健壮性/性能，建议优化）\n- 文件:行号 建议\n"
    "✅ 亮点\n- 说明\n"
    "最后一行给出结论：通过 / 不通过（有 🔴 时）。"
    "评审要具体，引用真实行号和代码片段，不要泛泛而谈。"
)


def review_file(path: Path) -> str:
    code = path.read_text(encoding="utf-8")
    user = (
        f"请评审这个文件：{path}\n"
        f"（共 {code.count(chr(10)) + 1} 行）\n\n"
        f"```python\n{code}\n```"
    )
    return stream_chat(REVIEW_SYSTEM, user)


def main() -> None:
    parser = argparse.ArgumentParser(description="agnes-2.5-pro 交叉评审")
    parser.add_argument("paths", nargs="*", help="要评审的文件")
    parser.add_argument("--all", action="store_true", help="评审 mobileflow/ 全部 .py")
    parser.add_argument("--gate", action="store_true", help="有 🔴 严重问题则 exit 1")
    args = parser.parse_args()

    if args.all:
        paths = sorted(Path("mobileflow").glob("*.py"))
    else:
        paths = [Path(p) for p in args.paths]
    if not paths:
        print("没有文件要评审")
        sys.exit(1)

    has_critical = False
    for p in paths:
        print(f"\n{'='*50}\n📄 评审: {p}")
        try:
            result = review_file(p)
        except Exception as e:
            print(f"  ❌ 评审失败: {e}")
            continue
        print(result)
        if "🔴" in result and "不通过" in result:
            has_critical = True

    if args.gate and has_critical:
        print("\n⛔ 存在 🔴 严重问题，评审未通过")
        sys.exit(1)
    print("\n✅ 评审完成")


if __name__ == "__main__":
    main()
