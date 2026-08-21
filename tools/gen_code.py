#!/usr/bin/env python3
"""GLM-5.2 流式代码生成器 —— 用商汤渠道生成完整代码文件。

用法:
    python3 tools/gen_code.py "用Python写一个xxx模块" -o mobileflow/xxx.py
    python3 tools/gen_code.py "写测试覆盖 mobileflow/ui_tree.py" -o tests/test_ui_tree.py

关键: stream=true 绕开商汤 max_tokens 预留配额（非流式 max_tokens≥1000 必 429）
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request


def read_env() -> dict[str, str]:
    env = {}
    with open("/opt/data/.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def gen_code(prompt: str, model: str = "glm-5.2") -> str:
    """流式调用 GLM-5.2 生成代码。"""
    env = read_env()
    key = env.get("SENSENOVA_API_KEY", "")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是资深 Python 工程师。直接输出完整、可运行的代码，"
                "不要解释性前言；如果代码较长用 ```python 代码块包裹。",
            },
            {"role": "user", "content": prompt},
        ],
        "reasoning_effort": "none",  # 商汤思考模型必须关
        "max_tokens": 8192,
        "stream": True,
    }
    req = urllib.request.Request(
        "https://token.sensenova.cn/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    t0 = time.time()
    parts: list[str] = []
    finish = "unknown"
    try:
        resp = urllib.request.urlopen(req, timeout=300)
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
                        finish = "DONE"
                        continue
                    try:
                        d = json.loads(data)
                        delta = d["choices"][0].get("delta", {})
                        if delta.get("content"):
                            parts.append(delta["content"])
                        if d["choices"][0].get("finish_reason"):
                            finish = d["choices"][0]["finish_reason"]
                    except Exception:
                        pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")
    full = "".join(parts)
    print(f"✅ GLM-5.2 生成完成: {len(full)} 字符, {time.time()-t0:.1f}s, finish={finish}")
    return full


def strip_code_fence(text: str) -> str:
    """去掉 ```python ... ``` 围栏。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        lines = lines[1:]  # 去掉开头的 ```python
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="GLM-5.2 流式代码生成")
    parser.add_argument("prompt", help="生成需求")
    parser.add_argument("-o", "--output", required=True, help="输出文件路径")
    parser.add_argument("--model", default="glm-5.2")
    args = parser.parse_args()

    code = gen_code(args.prompt, args.model)
    code = strip_code_fence(code)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"📁 已写入 {args.output} ({len(code)} 字符)")
    print("--- 前 300 字符预览 ---")
    print(code[:300])


if __name__ == "__main__":
    main()
