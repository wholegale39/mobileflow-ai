"""LLM 用例生成 —— 自然语言需求 → 可执行技能(YAML) + 校验。

闭环: 测试人员用自然语言描述场景 → LLM 生成 skills 格式步骤 → 结构校验 → 存为
YAML 到技能目录(与 skills.py 共用格式，可直接被 agent.run 执行)。

支持:
- generate(natural_language, llm) -> skill dict
- validate(skill) -> 校验步骤动作族合法性
- save(skill, path) -> 写 YAML

零新依赖（复用 LlmClient + PyYAML）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

# 需 target 的动作(可缺省但提示)
_NEEDS_TARGET = {"click", "long_click", "double_click", "wait", "input"}
# input 额外需 text
_NEEDS_TEXT = {"input"}

# 合法动作族（driver.execute_action 支持的全部动作前缀/名）
_VALID_ACTIONS = {
    "click", "long_click", "double_click", "coordinate_click", "visual_click",
    "input", "swipe", "drag_and_drop", "open_app", "home", "back", "key_event",
    "wait", "done", "scroll",
    # 断言族
    "assert_text_exists", "assert_text_gone", "assert_text_contains",
    "assert_visible", "assert_memory", "assert_network",
    # 幂等读取
    "screenshot", "get_text",
}

_PROMPT_TEMPLATE = '''你是移动端自动化测试专家。根据需求生成可执行测试用例（技能 JSON 格式）。

需求: __REQUIREMENT__
应用: __APP__

输出要求（严格只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字）:
{"name": "用例名(简短)", "description": "用例描述", "params": {"参数名": "说明"}, "steps": [{"action": "click", "target": {"text": "登录"}}, {"action": "input", "target": {"resource_id": "username"}, "text": "{param}"}]}

可用动作: __ACTIONS__
- click/long_click/double_click: target 用 {"text": ...} 或 {"resource_id": ...}
- input: target + text(可用 {param} 参数占位)
- open_app: {"package": ...} 或 {"name": ...}
- wait: 等 {"text": ...} 出现
- assert_text_exists/assert_text_gone/assert_text_contains: 断言
- done: 结束

步骤要覆盖: 前置操作 → 主流程 → 结果断言。每个步骤 action 必须来自可用动作列表。
参数用 {param} 占位，并在 params 里声明。'''


def _build_prompt(requirement: str, app: str, actions: str) -> str:
    # 防提示词注入: 对需求/应用名中的模板占位符做转义, 避免用户输入污染结构
    esc = lambda s: (s.replace("__REQUIREMENT__", "<REQ>")
                     .replace("__APP__", "<APP>").replace("__ACTIONS__", "<ACT>"))
    return (_PROMPT_TEMPLATE
            .replace("__REQUIREMENT__", esc(requirement))
            .replace("__APP__", esc(app))
            .replace("__ACTIONS__", actions))


def generate(requirement: str, llm, *, app: str = "", model: str | None = None) -> dict[str, Any]:
    """自然语言需求 → 技能格式用例。

    Args:
        requirement: 自然语言用例需求。
        llm: LlmClient 实例（需有 chat_raw 公开方法）。
        app: 被测应用名(可选，写入提示词)。
        model: 覆盖模型(可选)。
    """
    prompt = _build_prompt(requirement, app or "未知", ", ".join(sorted(_VALID_ACTIONS)))
    raw = llm.chat_raw(prompt, model=model, max_tokens=1024)
    if not raw:
        raise ValueError("用例生成失败: LLM 返回空内容")
    skill = _parse(raw)
    if not skill:
        raise ValueError("用例生成失败: 未能解析出合法 JSON（返回原文: " + raw[:120] + "）")
    skill.setdefault("name", requirement[:20])
    skill.setdefault("description", requirement)
    skill.setdefault("params", {})
    skill.setdefault("steps", [])
    return skill


def validate(skill: dict[str, Any]) -> dict[str, Any]:
    """校验技能结构合法性。返回 {"ok": True} 或 {"ok": False, "errors": [...]}。"""
    errors: list[str] = []
    if not skill.get("name"):
        errors.append("缺 name")
    steps = skill.get("steps", [])
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("steps 需为非空数组")
    else:
        for i, s in enumerate(steps):
            act = s.get("action") if isinstance(s, dict) else None
            if act not in _VALID_ACTIONS:
                errors.append(f"步骤{i}: 非法动作 {act}")
                continue
            if act in _NEEDS_TARGET and not s.get("target"):
                errors.append(f"步骤{i}: {act} 缺 target")
            if act in _NEEDS_TEXT and not s.get("text"):
                errors.append(f"步骤{i}: input 缺 text")
    # 参数占位一致性: steps 里用的 {x} 都应在 params 声明
    raw = json.dumps(steps, ensure_ascii=False)
    used = set(re.findall(r"\{(\w+)\}", raw))
    params = set(skill.get("params", {}).keys()) if isinstance(skill.get("params"), dict) else set()
    undeclared = used - params
    if undeclared:
        errors.append(f"参数未声明: {sorted(undeclared)}(steps 引用但 params 缺失)")
    return {"ok": not errors, "errors": errors}


def save(skill: dict[str, Any], path: str | Path) -> Path:
    """校验通过后写 YAML。"""
    res = validate(skill)
    if not res["ok"]:
        raise ValueError("用例校验未通过: " + "; ".join(res["errors"]))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(skill), encoding="utf-8")
    return path


def sanitize_filename(name: str) -> str:
    """把用例名消毒为安全文件名（防路径穿越/非法字符）。"""
    safe = re.sub(r"[^\w\w\-\u4e00-\u9fff]+", "_", name)  # 保留中文/字母/数字/-/_
    safe = safe.strip("_") or "case"
    return safe[:60]  # 限长


def generate_and_save(
    requirement: str, llm, *, app: str = "", out_dir: str | Path = "", model: str | None = None
) -> Path:
    """一步到位: 生成 → 校验 → 保存，返回 YAML 路径。"""
    skill = generate(requirement, llm, app=app, model=model)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return save(skill, out_dir / f"{sanitize_filename(skill['name'])}.yaml")


# ---------- 内部 ----------

def _parse(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    # 容错: 尝试直接从原文解析(最常见情况)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # 兜底: 提取 ```json ... ``` 代码块(支持多代码块,逐个尝试)
    for block in re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL):
        try:
            obj = json.loads(block.strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None
