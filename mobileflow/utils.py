"""mobileflow 通用工具。"""
from __future__ import annotations

from typing import Any


def escape_xpath_text(text: str) -> str:
    """转义 XPath 双引号字符串内的文本（防注入/解析错误）。

    注意：仅转义反斜杠和双引号。单引号在双引号包裹的 XPath 字符串内
    是普通字符，转义反而会篡改查询文本（如 it's → it\'s）。
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def action_to_desc(action: dict[str, Any]) -> str:
    """把动作 dict 转成人类可读的一句话（供恢复器/日志描述失败动作用）。"""
    act = action.get("action", "")
    t = action.get("target") or {}
    if act in ("click", "long_click", "double_click"):
        if t.get("text"):
            return f"{act}(text={t['text']!r})"
        if t.get("resource_id"):
            return f"{act}(resource_id={t['resource_id']!r})"
        if t.get("index") is not None:
            return f"{act}(index={t['index']})"
    if act == "input":
        return f"input(text={action.get('text')!r}) -> {t}"
    if act == "coordinate_click":
        return f"coordinate_click(x={action.get('x')}, y={action.get('y')})"
    if act == "swipe":
        return f"swipe({action.get('start')}→{action.get('end')})"
    if act == "drag":
        return f"drag({action.get('from')}→{action.get('to')})"
    if act == "scroll":
        return f"scroll({action.get('direction')})"
    if act == "input_key":
        return f"input_key(keycode={action.get('keycode')})"
    return f"{act}({action})"


def parse_llm_json(raw: str) -> dict[str, Any]:
    """容错解析 LLM 输出的 JSON（去代码块围栏/首尾废话），失败抛 ValueError。

    供 LlmClient 决策解析用。需要"返回 None"的宽松版本见 usecase._parse。
    """
    import json
    import re
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 输出无 JSON: {raw[:120]}")
    try:
        obj = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e} — {raw[:120]}")
    obj = _require_action(obj, raw)
    return obj


def _require_action(obj: dict, raw: str) -> dict:
    if not isinstance(obj, dict) or "action" not in obj:
        raise ValueError(f"JSON 缺 action 字段: {raw[:120]}")
    return obj
