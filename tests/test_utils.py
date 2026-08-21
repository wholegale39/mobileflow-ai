"""测试 utils 通用工具。"""
from __future__ import annotations

from mobileflow.utils import escape_xpath_text


def test_escape_xpath_backslash_and_quote():
    assert escape_xpath_text('a"b\\c') == 'a\\"b\\\\c'


def test_escape_xpath_apostrophe_preserved():
    """单引号在双引号包裹的 XPath 内是普通字符，不应被转义。"""
    assert escape_xpath_text("it's") == "it's"


def test_escape_xpath_empty():
    assert escape_xpath_text("") == ""
