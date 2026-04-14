"""板块文件 (.dat) 解析逻辑。"""

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.finance import TdxBlock


def parse_block_dat(data: bytes, filename: str = "") -> list["TdxBlock"]:
    """解析通达信 .dat 板块文件内容。

    格式：
      Header: 384 字节（跳过）
      Count:  2 字节 (uint16 LE)
      Body:   每条记录 2813 字节 (9s + H + H + 2800s)
    """
    from ..models.finance import TdxBlock

    if len(data) < 386:
        return []

    pos = 384
    (count,) = struct.unpack("<H", data[pos:pos+2])
    pos += 2

    results: list[TdxBlock] = []

    # 推断板块分类 (0=行业, 1=地域, 2=概念, 3=风格)
    category = 0
    if "zs" in filename:
        category = 0
    elif "gn" in filename:
        category = 2
    elif "fg" in filename:
        category = 3

    for _ in range(count):
        if len(data) < pos + 2813:
            break

        # 板块元数据 (9 字节名称 + 2 字节股票数 + 2 字节类型)
        name_b = data[pos:pos+9]
        stock_count, _type = struct.unpack("<HH", data[pos+9:pos+13])
        name = name_b.decode("gbk", errors="replace").strip("\x00")

        # 股票代码区 (2800 字节，每只股票 7 字节)
        codes: list[str] = []
        codes_start = pos + 13
        # 安全检查：stock_count 不应超过 400 (2800 / 7)
        actual_count = min(stock_count, 400)
        for i in range(actual_count):
            c_start = codes_start + i * 7
            c_raw = data[c_start:c_start+7]
            code = c_raw.decode("ascii", errors="replace").strip("\x00")
            if code:
                codes.append(code)

        results.append(TdxBlock(
            name=name,
            category=category,
            count=stock_count,
            codes=codes,
        ))

        # 跳过整个 2813 字节的记录块
        pos += 2813

    return results
