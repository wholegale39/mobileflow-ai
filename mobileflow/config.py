"""启动配置校验 —— 在真正调用前发现配置问题，给出清晰错误。

校验项（可配置）：
- LLM: MOBILEFLOW_API_KEY 存在且非空（可选轻量连通性探测）
- Vision: MOBILEFLOW_VISION_API_KEY 存在（仅 --vision 时必需）
- 平台目录/轨迹目录可写

设计：校验是即时、廉价的本地检查，不发起真实 LLM 请求（避免费 token/触发限流）；
key 的"有效性"用格式 + 可选 probe 验证。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# key 前缀白名单（仅做格式初筛，防止配成明显错误值如 "dummy"/"xxx"）
_KEY_PREFIXES = ("sk-", "Bearer ", "wrk-", "eyJ")


class ConfigError(RuntimeError):
    """配置校验失败。"""


def _load_env(path: str | Path | None = None) -> dict[str, str]:
    """读取 .env（支持路径参数，默认不动）。"""
    env: dict[str, str] = {}
    p = Path(path) if path else None
    if not p or not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
    return env


def check_llm(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    strict_key: bool = True,
) -> dict[str, Any]:
    """校验 LLM 配置。

    Args:
        strict_key: True 时要求 key 非空且不像占位值；False 仅检查 base_url 格式。
    """
    url = base_url or os.environ.get("MOBILEFLOW_BASE_URL", "")
    key = api_key or os.environ.get("MOBILEFLOW_API_KEY", "")
    issues: list[str] = []

    if strict_key and not key:
        issues.append("MOBILEFLOW_API_KEY 未设置（环境变量或 LlmClient(api_key=...)）")
    elif strict_key and key and not any(key.startswith(p) for p in _KEY_PREFIXES):
        issues.append(
            f"MOBILEFLOW_API_KEY 格式可疑（值以 {key[:6]}... 开头，"
            "正常应以 sk-/eyJ/Bearer 等开头），确认是否配了占位值"
        )
    if url and not url.startswith(("http://", "https://")):
        issues.append(f"MOBILEFLOW_BASE_URL 不是合法 URL: {url}")

    result = {"ok": not issues, "issues": issues, "model": model or os.environ.get("MOBILEFLOW_MODEL", "")}
    if issues:
        raise ConfigError("LLM 配置校验失败:\n  - " + "\n  - ".join(issues))
    return result


def check_vision(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """校验 Vision 配置。仅 enabled=True 时要求 key。"""
    if not enabled:
        return {"ok": True, "issues": [], "enabled": False}
    issues: list[str] = []
    key = api_key or os.environ.get("MOBILEFLOW_VISION_API_KEY", "") or os.environ.get("AGNES_API_KEY", "")
    url = base_url or os.environ.get("MOBILEFLOW_VISION_BASE_URL", "")
    if not key:
        issues.append("视觉通道已启用，但 MOBILEFLOW_VISION_API_KEY（或 AGNES_API_KEY）未设置")
    if url and not url.startswith(("http://", "https://")):
        issues.append(f"MOBILEFLOW_VISION_BASE_URL 不是合法 URL: {url}")
    result = {"ok": not issues, "issues": issues, "enabled": True}
    if issues:
        raise ConfigError("Vision 配置校验失败:\n  - " + "\n  - ".join(issues))
    return result


def check_paths(*paths: str | Path, must_writable: bool = False) -> dict[str, Any]:
    """校验目录可写。"""
    issues: list[str] = []
    for p in paths:
        p = Path(p).expanduser()
        if must_writable:
            parent = p.parent if p.is_file() or p.suffix else p
            parent.mkdir(parents=True, exist_ok=True)
            try:
                probe = parent / ".mobileflow_write_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
            except OSError as e:
                issues.append(f"目录不可写: {parent} ({e})")
    result = {"ok": not issues, "issues": issues}
    if issues:
        raise ConfigError("路径校验失败:\n  - " + "\n  - ".join(issues))
    return result


def validate_all(*, vision_enabled: bool = False, strict_key: bool = True) -> dict[str, Any]:
    """一键校验全部配置，返回汇总；任一失败抛 ConfigError（含全部问题）。

    收集所有问题后统一抛出，方便一次性看到全部配置缺陷。
    """
    all_issues: list[str] = []
    summary: dict[str, Any] = {}
    try:
        summary["llm"] = check_llm(strict_key=strict_key)
    except ConfigError as e:
        all_issues.append("LLM: " + e.args[0].replace("\n", " | "))
    try:
        summary["vision"] = check_vision(enabled=vision_enabled)
    except ConfigError as e:
        all_issues.append("Vision: " + e.args[0].replace("\n", " | "))
    if all_issues:
        raise ConfigError("配置校验失败，请修正后重试:\n  - " + "\n  - ".join(all_issues))
    summary["ok"] = True
    return summary
