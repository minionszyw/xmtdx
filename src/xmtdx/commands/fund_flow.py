"""历史资金流向命令 (Category 22)。"""

import struct

from ..codec.volume import _decode_volume
from ..models.enums import Market
from ..models.stats import HistoricalFundFlow
from .base import BaseCommand


class GetHistoryFundFlowCmd(BaseCommand[list[HistoricalFundFlow]]):
    """获取历史日线资金流向序列。"""

    def __init__(self, market: Market, code: str, start: int, count: int) -> None:
        self.market = market
        self.code = code.encode("utf-8")
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
            22,
            1,
            self.start,
            self.count,
            0,
            0,
            0,
        )

    def parse_response(self, body: bytes) -> list[HistoricalFundFlow]:
        # 响应格式：9字节头 + 2字节数量 + 每条记录 36 字节
        if len(body) < 11:
            return []
            
        (num,) = struct.unpack("<H", body[9:11])
        pos = 11
        results = []
        
        for _ in range(num):
            if len(body) < pos + 36:
                break
            
            # 记录格式：4字节日期 + 8个4字节自定义浮点金额
            # [0]日期, [1..4]流入(超/大/中/小), [5..8]流出(超/大/中/小)
            raw_data = struct.unpack("<IIIIIIIII", body[pos:pos+36])
            
            raw_date = raw_data[0]
            year = raw_date // 10000
            month = (raw_date // 100) % 100
            day = raw_date % 100
            
            results.append(HistoricalFundFlow(
                year=year, month=month, day=day,
                super_in=_decode_volume(raw_data[1]),
                large_in=_decode_volume(raw_data[2]),
                medium_in=_decode_volume(raw_data[3]),
                small_in=_decode_volume(raw_data[4]),
                super_out=_decode_volume(raw_data[5]),
                large_out=_decode_volume(raw_data[6]),
                medium_out=_decode_volume(raw_data[7]),
                small_out=_decode_volume(raw_data[8]),
            ))
            pos += 36
            
        return results
