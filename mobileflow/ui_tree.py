"""UI 树压缩 —— Appium page source (XML) → 紧凑文本。

GLM-5.2 max_tokens 只有 300，UI 树必须压缩到几行内：
- 只保留 text / content-desc / resource-id / bounds / clickable
- 去掉坐标噪音，用紧凑单行格式
- 超长截断（按元素数）
"""
from __future__ import annotations

import re


def compress_page_source(xml: str, max_elements: int = 60, *, include_bounds: bool = True) -> str:
    """XML page source → 压缩文本列表。"""
    nodes = _parse_nodes(xml)
    lines = []
    for i, node in enumerate(nodes[:max_elements]):
        lines.append(_format_node(i, node, include_bounds=include_bounds))
    if len(nodes) > max_elements:
        lines.append(f"...（还有 {len(nodes) - max_elements} 个元素未显示）")
    return "\n".join(lines) if lines else "（空屏幕）"


def _parse_nodes(xml: str) -> list[dict[str, str]]:
    """轻量 XML 解析：提取每个节点标签的属性。"""
    nodes: list[dict[str, str]] = []
    # 匹配 <node ... /> 或 <node ...>（自闭合或开标签）
    pattern = re.compile(r"<node\s([^>]*?)/?>", re.DOTALL)
    for m in pattern.finditer(xml):
        attrs = _parse_attrs(m.group(1))
        if attrs:
            nodes.append(attrs)
    return nodes


def _parse_attrs(raw: str) -> dict[str, str]:
    """解析 key="value" 属性对。"""
    attrs: dict[str, str] = {}
    for m in re.finditer(r'(\w+[-\w]*)\s*=\s*"([^"]*)"', raw):
        attrs[m.group(1)] = m.group(2)
    return attrs


def _format_node(index: int, node: dict[str, str], *, include_bounds: bool = True) -> str:
    """单节点压缩格式：{index} [text] content-desc (resource-id) {clickable}@bounds"""
    text = node.get("text", "").strip()
    desc = node.get("content-desc", "").strip()
    rid = node.get("resource-id", "").strip()
    clickable = node.get("clickable") == "true"
    bounds = node.get("bounds", "")

    parts = [f"[{index}]"]
    label = text or desc
    if label:
        parts.append(f"「{label[:40]}」")
    if rid:
        parts.append(f"({rid.split('/')[-1]})")
    if clickable:
        parts.append("{可点}")
    if include_bounds and bounds:
        parts.append(bounds)
    return " ".join(parts)
