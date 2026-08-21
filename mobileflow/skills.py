"""技能库 —— 预定义任务模板（面向未来技能标准化）。

技能 = 命名 + 描述 + 步骤序列（动作或子任务提示词）+ 参数槽。
格式：YAML，默认目录 ~/.mobileflow/skills/。
未来演进：对齐 MCP mobile 协议/系统级 UI 语义标准时，技能可导出为标准格式。
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SKILLS = {
    "open_app": {
        "name": "打开应用",
        "description": "打开指定应用（按名称匹配桌面图标）",
        "keywords": ["打开", "启动", "进入"],
        "params": {"app": "应用名称，如 微信"},
        "steps": [
            {"action": "home"},
            {"action": "open_app", "package": "{app}"},
        ],
    },
    "scroll_find": {
        "name": "滚动查找",
        "description": "在当前页面滚动查找目标文本",
        "keywords": ["滚动", "查找", "找"],
        "params": {"target": "要找的文本"},
        "steps": [
            {"action": "scroll", "direction": "down"},
            {"action": "click", "target": {"text": "{target}"}, "optional": True},
        ],
    },
}


class SkillLibrary:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.environ.get("MOBILEFLOW_SKILLS", "~/.mobileflow/skills")).expanduser()
        self.skills: dict[str, Any] = {}
        self._load_defaults()
        self._load_dir()

    def _load_defaults(self) -> None:
        # deepcopy 隔离：外部修改技能字典不污染 DEFAULT_SKILLS
        self.skills.update({k: copy.deepcopy(v) for k, v in DEFAULT_SKILLS.items()})

    def _load_dir(self) -> None:
        if not self.path.exists():
            return
        for f in sorted(self.path.glob("*.yaml")) + sorted(self.path.glob("*.yml")):
            try:
                skill = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(skill, dict) and skill.get("name"):
                    self.skills[skill["name"]] = skill
            except yaml.YAMLError:
                continue

    def match(self, task: str) -> dict[str, Any] | None:
        """按技能关键词/描述匹配（返回最佳匹配）。

        优先用技能显式 keywords（精确）；无 keywords 的技能用描述整词粗匹配，
        避免单字误命中。
        """
        best, best_score = None, 0
        for skill in self.skills.values():
            keywords = skill.get("keywords") or []
            desc = skill.get("description", "")
            score = 0
            if keywords:
                score = sum(2 for kw in keywords if kw in task)
            else:
                score = sum(
                    1 for kw in re.findall(r"[一-鿿a-zA-Z]{2,}", task)
                    if kw in desc
                )
            if score > best_score:
                best, best_score = skill, score
        return best if best_score > 0 else None

    def render_steps(self, skill: dict[str, Any], params: dict[str, Any]) -> list[dict[str, Any]]:
        """技能步骤 + 参数 → 动作序列（{param} 槽填充，缺参数抛错）。"""
        # 提取所有需要的参数槽
        raw = json.dumps(skill.get("steps", []), ensure_ascii=False)
        needed = set(re.findall(r"\{(\w+)\}", raw))
        missing = needed - set(params)
        if missing:
            raise ValueError(f"技能「{skill.get('name')}」缺参数: {sorted(missing)}")
        steps = []
        for step in skill.get("steps", []):
            s = dict(step)
            for key, val in params.items():
                s = _fill(s, "{" + key + "}", val)
            steps.append(s)
        return steps

    def add(self, skill: dict[str, Any]) -> None:
        """新增技能到本地目录。"""
        self.path.mkdir(parents=True, exist_ok=True)
        fname = skill.get("name", "skill") + ".yaml"
        (self.path / fname).write_text(
            yaml.safe_dump(skill, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        self.skills[skill.get("name", "")] = skill

    def list(self) -> list[str]:
        return list(self.skills.keys())


def _fill(obj: Any, key: str, val: str) -> Any:
    """递归替换 {param} 槽。"""
    if isinstance(obj, dict):
        return {k: _fill(v, key, val) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, key, val) for v in obj]
    if isinstance(obj, str):
        return obj.replace(key, val)
    return obj
