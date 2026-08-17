"""可选 pandas 转换工具。"""

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from importlib import import_module
from typing import Any


def to_dataframe(records: Iterable[object], *, include_raw: bool = False) -> Any:
    """将 xmtdx dataclass 记录转换为 pandas.DataFrame。

    pandas 仍是可选依赖；默认排除 ``_raw`` 等内部字段。
    """
    rows: list[dict[str, object]] = []
    for record in records:
        if not is_dataclass(record) or isinstance(record, type):
            raise TypeError("records 中的元素必须是 dataclass 实例")
        row: dict[str, object] = {}
        for item in fields(record):
            if not include_raw and item.name.startswith("_"):
                continue
            row[item.name] = getattr(record, item.name)
        rows.append(row)

    try:
        pandas = import_module("pandas")
    except ImportError as error:
        raise ImportError('需要 pandas，请安装 xmtdx[pandas]') from error
    return pandas.DataFrame(rows)
