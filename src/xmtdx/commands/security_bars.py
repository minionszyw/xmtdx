"""获取 K 线数据命令（支持全部周期）。"""

import struct

from .._binary import unpack_from
from ..codec.datetime_ import get_datetime
from ..codec.price import get_price
from ..codec.volume import get_volume
from ..models.bar import SecurityBar
from ..models.enums import KlineCategory, Market
from .base import BaseCommand


class GetSecurityBarsCmd(BaseCommand[list[SecurityBar]]):
    """获取指定股票的 K 线数据。

    Args:
        market:   市场（SH/SZ）
        code:     6位股票代码（字符串）
        category: K线周期
        start:    起始行（0 = 最新；分页时递增）
        count:    返回条数（最多 800）
    """

    def __init__(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.category = category
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # Header (12 bytes) + Payload (28 bytes) = 40 bytes
        return struct.pack(
            "<HIHHHH6sHHHHIIH",
            0x010C,
            0x01016408,
            0x001C,
            0x001C,
            0x052D,
            int(self.market),
            self.code,
            int(self.category),
            1,
            self.start,
            self.count,
            0,
            0,
            0,
        )

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        (ret_count,) = unpack_from("<H", body, 0, "security_bars header")
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(self.category)

        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)

            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)

            # 差分还原（与 pytdx 完全一致）
            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff

            bars.append(
                SecurityBar(
                    open=open_abs / 1000.0,
                    close=close_abs / 1000.0,
                    high=high_abs / 1000.0,
                    low=low_abs / 1000.0,
                    vol=vol,
                    amount=amount,
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    _raw=body[record_start:pos],
                )
            )

        return bars


class GetIndexBarsCmd(GetSecurityBarsCmd):
    """获取指数 K 线（请求格式与股票 K 线相同，服务器端按指数逻辑处理）。

    实际上通达信服务器对股票代码前缀自动判断指数/股票，
    此子类仅作语义区分，无额外逻辑。
    """
