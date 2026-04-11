"""除权除息信息命令。

修复 pytdx Bug #1：循环内从正确的 pos 位置读取 market/code，
不再始终读取 body[:7]。
"""

import struct

from ..codec.datetime_ import get_datetime
from ..models.enums import Market
from ..models.finance import XDXR_CATEGORY_NAMES, XdxrRecord
from .base import BaseCommand


class GetXdxrInfoCmd(BaseCommand[list[XdxrRecord]]):
    """获取除权除息历史记录。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c1f18760001 0b000b000f000100".replace(" ", ""))
        return header + struct.pack("<B6s", int(self.market), self.code)

    def parse_response(self, body: bytes) -> list[XdxrRecord]:
        if len(body) < 11:
            return []

        pos = 9  # 跳过9字节（market+code+未知）
        (num,) = struct.unpack_from("<H", body, pos)
        pos += 2

        records: list[XdxrRecord] = []

        for _ in range(num):
            record_start = pos

            # Bug #1 修复：从当前 pos 读，而非 body[:7]
            if pos + 7 > len(body):
                break
            market_b, code_b = struct.unpack_from("<B6s", body, pos)
            pos += 7
            pos += 1  # 跳过1个未知字节

            year, month, day, _hour, _min, pos = get_datetime(9, body, pos)
            (category,) = struct.unpack_from("<B", body, pos)
            pos += 1

            if pos + 16 > len(body):
                break

            chunk = body[pos : pos + 16]
            pos += 16

            rec = XdxrRecord(
                market=Market(market_b),
                code=code_b.decode("utf-8").rstrip("\x00"),
                year=year,
                month=month,
                day=day,
                category=category,
                name=XDXR_CATEGORY_NAMES.get(category, str(category)),
                _raw=body[record_start:pos],
            )

            if category == 1:
                fenhong, peigujia, songzhuangu, peigu = struct.unpack("<ffff", chunk)
                rec.fenhong = fenhong
                rec.peigujia = peigujia
                rec.songzhuangu = songzhuangu
                rec.peigu = peigu
            elif category in (11, 12):
                _, _, suogu, _ = struct.unpack("<IIfI", chunk)
                rec.suogu = suogu
            elif category in (13, 14):
                xingquanjia, _, fenshu, _ = struct.unpack("<fIfI", chunk)
                rec.xingquanjia = xingquanjia
                rec.fenshu = fenshu
            else:
                # 股本变动类：4个 uint32，代表前后流通/总股本
                ql_raw, qz_raw, hl_raw, hz_raw = struct.unpack("<IIII", chunk)
                rec.panqian_liutong = _decode_share_count(ql_raw)
                rec.qian_zongguben = _decode_share_count(qz_raw)
                rec.panhou_liutong = _decode_share_count(hl_raw)
                rec.hou_zongguben = _decode_share_count(hz_raw)

            records.append(rec)

        return records


def _decode_share_count(raw: int) -> float:
    """股本数量解码（uint32 → 股数）。

    pytdx 使用 get_volume 但会产生错误结果（xdxr Bug #1 注释）。
    目前保持与服务器原始整数一致，待进一步逆向确认正确解码方式。
    """
    return float(raw)
