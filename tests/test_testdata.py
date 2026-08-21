"""测试 testdata 测试数据工厂。"""
from __future__ import annotations

from mobileflow.testdata import (
    boundaries_int,
    boundary_strings,
    credit_card_like,
    fill_template,
    load_table,
    parametrize,
    random_chinese_name,
    random_email,
    random_phone,
    random_string,
)


def test_boundaries_int():
    b = boundaries_int(3, 10)
    assert b == [2, 3, 4, 9, 10, 11]


def test_boundaries_int_single():
    b = boundaries_int(5, 5)
    assert 5 in b and 4 in b and 6 in b


def test_boundaries_strings():
    b = boundary_strings(2, 4, char="x")
    lens = sorted({len(s) for s in b})
    assert lens == [1, 2, 3, 4, 5]


def test_parametrize_two_dims():
    cases = parametrize(a=[1, 2], b=["x", "y"])
    assert len(cases) == 4
    assert {"a": 1, "b": "x"} in cases
    assert {"a": 2, "b": "y"} in cases


def test_parametrize_empty():
    assert parametrize() == [{}]


def test_fill_template():
    tpl = {"user": "{u}", "msg": "hello {u}, code={c}"}
    cases = parametrize(u=["a", "b"], c=[1])
    insts = fill_template(tpl, cases)
    assert insts == [{"user": "a", "msg": "hello a, code=1"},
                     {"user": "b", "msg": "hello b, code=1"}]


def test_fill_template_nested():
    tpl = {"steps": [{"action": "input", "text": "{v}"}]}
    cases = parametrize(v=["ok"])
    assert fill_template(tpl, cases)[0]["steps"][0]["text"] == "ok"


def test_random_phone():
    p = random_phone()
    assert p.startswith("1") and len(p) == 11 and p.isdigit()


def test_random_email():
    assert "@" in random_email()


def test_random_chinese_name():
    n = random_chinese_name()
    assert 2 <= len(n) <= 3


def test_credit_card_like():
    cc = credit_card_like(length=16, sep=" ")
    assert cc.replace(" ", "") .isdigit() and len(cc.replace(" ", "")) == 16


def test_random_string():
    assert len(random_string(5)) == 5


def test_load_table_csv(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("user,pwd\nalice,111\nbob,222\n", encoding="utf-8")
    assert load_table(p) == [{"user": "alice", "pwd": "111"}, {"user": "bob", "pwd": "222"}]


def test_load_table_json(tmp_path):
    p = tmp_path / "d.json"
    p.write_text('[{"x":1},{"x":2}]', encoding="utf-8")
    assert len(load_table(p)) == 2


def test_load_table_missing(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_table(tmp_path / "nope.csv")
