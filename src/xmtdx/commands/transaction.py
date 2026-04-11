"""逐笔成交命令（当日 + 历史）。

修复 pytdx Bug #4：保留原被 _ 丢弃的最后一个字段为 unknown_last。
"""

import struct

from ..codec.datetime_ import get_time
from ..codec.price import get_price
from ..models.enums import Market
from ..models.timeseries import TransactionRecord
from .base import BaseCommand


class GetTransactionDataCmd(BaseCommand[list[TransactionRecord]]):
    """获取当日逐笔成交（分页，每次最多 800 条）。"""

    def __init__(self, market: Market, code: str, start: int, count: int = 800) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c170801010 10e000e00c50f".replace(" ", ""))
        return header + struct.pack("<H6sHH", int(self.market), self.code, self.start, self.count)



    def parse_response(self, body: bytes) -> list[TransactionRecord]:
        return _parse_transaction_body(body)


class GetHistoryTransactionDataCmd(BaseCommand[list[TransactionRecord]]):
    """获取历史某日逐笔成交（date 格式 YYYYMMDD，分页）。"""

    def __init__(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # 历史逐笔：header + pack("<IH6sHH", date, market, code, start, count)
        header = bytes.fromhex("0c013001000112001200b50f".replace(" ", ""))
        return header + struct.pack(
            "<IH6sHH", self.date, int(self.market), self.code, self.start, self.count
        )

    def parse_response(self, body: bytes) -> list[TransactionRecord]:
        # 历史逐笔：num(2) + 4字节填充；无"成交笔数"字段
        return _parse_history_transaction_body(body)


def _parse_transaction_body(body: bytes) -> list[TransactionRecord]:
    """当日逐笔：time + price + vol + num_orders + buyorsell + unknown"""
    (num,) = struct.unpack_from("<H", body, 0)
    pos = 2
    last_price = 0
    records: list[TransactionRecord] = []

    for _ in range(num):
        record_start = pos
        hour, minute, pos = get_time(body, pos)
        price_diff, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        _num_orders, pos = get_price(body, pos)  # 成交笔数（当日独有）
        buyorsell, pos = get_price(body, pos)
        unknown_last, pos = get_price(body, pos)  # Bug #4 修复：不再丢弃
        last_price += price_diff
        records.append(TransactionRecord(
            hour=hour, minute=minute,
            price=last_price / 100.0, vol=vol, buyorsell=buyorsell,
            unknown_last=unknown_last, _raw=body[record_start:pos],
        ))

    return records


def _parse_history_transaction_body(body: bytes) -> list[TransactionRecord]:
    """历史逐笔：num(2) + skip(4) + [time + price + vol + buyorsell + unknown]"""
    (num,) = struct.unpack_from("<H", body, 0)
    pos = 6  # 2(num) + 4(skip)
    last_price = 0
    records: list[TransactionRecord] = []

    for _ in range(num):
        record_start = pos
        hour, minute, pos = get_time(body, pos)
        price_diff, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        buyorsell, pos = get_price(body, pos)      # 历史无 num_orders
        unknown_last, pos = get_price(body, pos)
        last_price += price_diff
        records.append(TransactionRecord(
            hour=hour, minute=minute,
            price=last_price / 100.0, vol=vol, buyorsell=buyorsell,
            unknown_last=unknown_last, _raw=body[record_start:pos],
        ))

    return records
