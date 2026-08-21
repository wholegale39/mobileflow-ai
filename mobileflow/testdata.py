"""测试数据工厂 —— 边界值 / 参数化 / 数据生成，让用例可复用。

面向"一个用例模板 × 多组数据"的测试：
- Boundaries: 给定区间/长度，产出 边界值集（min/max/略越界/空/超长）
- Parametrize: 把参数槽（skills 的 params / 用例变量）展开为多组组合
- Generators: 手机号/邮箱/中文名/随机字符串等常用测试数据生成
- Table: 从 CSV/JSON 读外部数据表

零新依赖（纯 stdlib + 已有 PyYAML）。
"""
from __future__ import annotations

import csv
import json
import random
import string
from pathlib import Path
from typing import Any, Iterable


# ---------- 边界值 ----------

def boundaries_int(lo: int, hi: int) -> list[int]:
    """整数区间边界值：{min-1, min, min+1, max-1, max, max+1}，去重排序。"""
    vals = {lo - 1, lo, lo + 1, hi - 1, hi, hi + 1}
    return sorted(vals)


def boundaries_len(min_len: int, max_len: int) -> list[int]:
    """字符串长度边界值（同整数逻辑，语义更明确）。"""
    return boundaries_int(min_len, max_len)


def boundary_strings(lo: int, hi: int, *, char: str = "a") -> list[str]:
    """按边界长度生成字符串：{len=min-1, min, min+1, max-1, max, max+1}。"""
    return [char * n for n in boundaries_len(lo, hi)]


# ---------- 参数化 ----------

def parametrize(**dims: Iterable[Any]) -> list[dict[str, Any]]:
    """笛卡尔积展开多维权值为参数字典。

    例: parametrize(user=["zhang","li"], pwd=["123","!@#"])
       -> [{"user":"zhang","pwd":"123"}, {"user":"zhang","pwd":"!@#"}, ...]
    """
    keys = list(dims)
    if not keys:
        return [{}]
    vals = [list(dims[k]) for k in keys]
    out: list[dict[str, Any]] = []
    _cartesian(out, keys, vals, {}, 0)
    return out


def _cartesian(out: list, keys: list[str], cols: list[list[Any]], cur: dict, i: int) -> None:
    if i == len(keys):
        out.append(dict(cur))
        return
    for v in cols[i]:
        cur[keys[i]] = v
        _cartesian(out, keys, cols, cur, i + 1)


def fill_template(template: dict[str, Any], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把参数字典填充进模板（{占位符} → 值），返回多份实例。"""
    out = []
    tpl_text = json.dumps(template, ensure_ascii=False)
    for case in cases:
        inst = json.loads(tpl_text)
        _deep_fill(inst, case)
        out.append(inst)
    return out


def _deep_fill(obj: Any, vals: dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            obj[k] = _deep_fill(v, vals)
    elif isinstance(obj, list):
        obj[:] = [_deep_fill(x, vals) for x in obj]
    elif isinstance(obj, str):
        for k, v in vals.items():
            obj = obj.replace(f"{{{k}}}", str(v))
        return obj
    return obj


# ---------- 数据生成器 ----------

def random_string(n: int = 8, *, chars: str | None = None) -> str:
    pool = chars or (string.ascii_letters + string.digits)
    return "".join(random.choices(pool, k=n))


def random_phone() -> str:
    prefix = random.choice(["138", "139", "150", "151", "186", "187", "176", "199"])
    return prefix + "".join(random.choices(string.digits, k=8))


def random_email(domain: str = "test.example") -> str:
    return f"user{random.randint(1000,9999)}@{domain}"


def random_chinese_name() -> str:
    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    chars = "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂英文辉"
    return random.choice(surnames) + random.choice(chars) + random.choice(chars + " ")


def credit_card_like(*, length: int = 16, sep: str = "") -> str:
    body = "".join(random.choices(string.digits, k=length))
    if sep:
        return sep.join(body[i : i + 4] for i in range(0, length, 4))
    return body


# ---------- 数据表（CSV/JSON）----------

def load_table(path: str | Path) -> list[dict[str, Any]]:
    """读 CSV 或 JSON 数据表，返回 dict 列表。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"数据表不存在: {p}")
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() in (".csv",):
        return list(csv.DictReader(text.splitlines()))
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"数据表格式不支持: {type(data)}")
