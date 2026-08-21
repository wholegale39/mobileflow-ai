"""mobileflow 通用工具。"""
from __future__ import annotations


def escape_xpath_text(text: str) -> str:
    """转义 XPath 双引号字符串内的文本（防注入/解析错误）。

    注意：仅转义反斜杠和双引号。单引号在双引号包裹的 XPath 字符串内
    是普通字符，转义反而会篡改查询文本（如 it's → it\\'s）。
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')
