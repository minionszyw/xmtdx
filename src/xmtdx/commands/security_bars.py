"""获取股票和指数 K 线数据。"""

import struct
from abc import abstractmethod
from typing import Generic, TypeVar

from .._binary import unpack_from
from ..codec.datetime_ import get_datetime
from ..codec.price import get_price
from ..codec.volume import get_volume
from ..models.bar import IndexBar, SecurityBar
from ..models.enums import KlineCategory, Market
from ..validation import validate_code, validate_count, validate_uint16
from .base import BaseCommand

_BarT = TypeVar("_BarT", bound=SecurityBar)


class _GetBarsCmd(BaseCommand[list[_BarT]], Generic[_BarT]):
    def __init__(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> None:
        self.market = market
        self.code = validate_code(code).encode("ascii")
        self.category = category
        self.start = validate_uint16(start, "start")
        self.count = validate_count(count, 800)

    def build_request(self) -> bytes:
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

    @property
    def _has_index_breadth(self) -> bool:
        return False

    @abstractmethod
    def _make_bar(
        self,
        *,
        open_: float,
        close: float,
        high: float,
        low: float,
        vol: float,
        amount: float,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        up_count: int,
        down_count: int,
        raw: bytes,
    ) -> _BarT: ...

    def parse_response(self, body: bytes) -> list[_BarT]:
        (ret_count,) = unpack_from("<H", body, 0, "bars header")
        pos = 2
        bars: list[_BarT] = []
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

            up_count = 0
            down_count = 0
            if self._has_index_breadth:
                up_count, down_count = unpack_from(
                    "<HH", body, pos, "index_bars breadth"
                )
                pos += 4

            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = close_abs

            bars.append(
                self._make_bar(
                    open_=open_abs / 1000.0,
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
                    up_count=up_count,
                    down_count=down_count,
                    raw=body[record_start:pos],
                )
            )

        return bars


class GetSecurityBarsCmd(_GetBarsCmd[SecurityBar]):
    """获取股票 K 线（单次最多 800 条）。"""

    def _make_bar(
        self,
        *,
        open_: float,
        close: float,
        high: float,
        low: float,
        vol: float,
        amount: float,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        up_count: int,
        down_count: int,
        raw: bytes,
    ) -> SecurityBar:
        return SecurityBar(
            open=open_, close=close, high=high, low=low, vol=vol, amount=amount,
            year=year, month=month, day=day, hour=hour, minute=minute, _raw=raw,
        )


class GetIndexBarsCmd(_GetBarsCmd[IndexBar]):
    """获取指数 K 线，并解析每条记录尾部的涨跌家数。"""

    @property
    def _has_index_breadth(self) -> bool:
        return True

    def _make_bar(
        self,
        *,
        open_: float,
        close: float,
        high: float,
        low: float,
        vol: float,
        amount: float,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        up_count: int,
        down_count: int,
        raw: bytes,
    ) -> IndexBar:
        return IndexBar(
            open=open_, close=close, high=high, low=low, vol=vol, amount=amount,
            year=year, month=month, day=day, hour=hour, minute=minute,
            _raw=raw, up_count=up_count, down_count=down_count,
        )
