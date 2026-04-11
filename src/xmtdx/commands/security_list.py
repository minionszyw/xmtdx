"""获取证券列表命令（每页最多1000条，按 start 分页）。

修复 pytdx Bug #2：GBK 解码使用 errors='replace'，截断多字节序列不再崩溃。
修复 pytdx Bug #3：pre_close 使用 get_price 解码，而非 get_volume。
"""

import struct

from .._binary import slice_bytes, unpack_from
from ..models.enums import Market
from ..models.security import SecurityInfo
from .base import BaseCommand

_RECORD_SIZE = 29


class GetSecurityListCmd(BaseCommand[list[SecurityInfo]]):
    """获取指定市场从 start 开始的证券列表。"""

    def __init__(self, market: Market, start: int) -> None:
        self.market = market
        self.start = start

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c01186401010600060050 04".replace(" ", ""))
        return header + struct.pack("<HH", int(self.market), self.start)

    def parse_response(self, body: bytes) -> list[SecurityInfo]:
        (num,) = unpack_from("<H", body, 0, "security_list header")
        pos = 2
        results: list[SecurityInfo] = []

        for _ in range(num):
            raw = slice_bytes(body, pos, _RECORD_SIZE, "security_list record")
            (
                code_bytes,
                volunit,
                name_bytes,
                _unknown1,    # 4字节，含义未明
                decimal_point,
                pre_close_raw,
                _unknown2,    # 4字节，含义未明
            ) = struct.unpack("<6sH8s4sBI4s", raw)

            code = code_bytes.decode("utf-8", errors="replace").rstrip("\x00")
            # Bug #2 修复：errors='replace' 避免截断 GBK 多字节序列时崩溃
            name = name_bytes.decode("gbk", errors="replace").rstrip("\x00")

            # Bug #3 修复：pre_close 不用 get_volume（成交量解码），
            # 而是直接将 uint32 当作价格整数（/ 100）
            # 实际服务器返回的 pre_close_raw 是 price * 100 的整数
            pre_close = pre_close_raw / 100.0

            results.append(
                SecurityInfo(
                    market=self.market,
                    code=code,
                    name=name,
                    volunit=volunit,
                    decimal_point=decimal_point,
                    pre_close=pre_close,
                    _raw=raw,
                )
            )
            pos += _RECORD_SIZE

        return results
