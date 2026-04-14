"""除权除息信息命令。

修复 pytdx Bug #1：循环内从正确的 pos 位置读取 market/code，
不再始终读取 body[:7]。
"""

import struct

from .._binary import slice_bytes, unpack_from
from ..codec.datetime_ import get_datetime
from ..codec.volume import _decode_volume
from ..exceptions import TdxDecodeError
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
            raise TdxDecodeError("xdxr_info body 过短")

        pos = 9  # 跳过9字节（market+code+未知）
        (num,) = unpack_from("<H", body, pos, "xdxr_info header")
        pos += 2

        records: list[XdxrRecord] = []

        for _ in range(num):
            record_start = pos

            # Bug #1 修复：从当前 pos 读，而非 body[:7]
            market_b, code_b = unpack_from("<B6s", body, pos, "xdxr_info record header")
            pos += 7
            slice_bytes(body, pos, 1, "xdxr_info record padding")
            pos += 1  # 跳过1个未知字节

            year, month, day, _hour, _min, pos = get_datetime(9, body, pos)
            (category,) = unpack_from("<B", body, pos, "xdxr_info category")
            pos += 1

            chunk = slice_bytes(body, pos, 16, "xdxr_info record body")
            pos += 16
            try:
                market = Market(market_b)
            except ValueError as e:
                raise TdxDecodeError(f"xdxr_info 非法 market 值: {market_b}") from e

            rec = XdxrRecord(
                market=market,
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
    """股本数量解码（通达信自定义4字节浮点 → 万股）。

    xdxr_info 的股本字段与成交量字段使用相同的自定义浮点编码，
    解码结果单位为万股，与 FinanceInfo.zong_guben / 10000 一致。
    """
    return _decode_volume(raw)
