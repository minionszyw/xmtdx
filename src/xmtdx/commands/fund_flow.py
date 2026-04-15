"""历史资金流向命令 (Category 22)。"""

import struct

from .._binary import slice_bytes, unpack_from
from ..codec.volume import _decode_volume
from ..exceptions import TdxDecodeError
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
        # 使用 0x052d 指令（K 线类指令）
        # 负载长度固定为 28 字节 (0x1c)
        payload_len = 0x1c
        header = struct.pack(
            "<HIHHH",
            0x010c,
            0x01016408, # 注意此处标志位与普通行情略有不同
            payload_len,
            payload_len,
            0x052d,
        )
        # 参数包：Market(B), Code(6s), Category(H=22), Unknown(H=1), Start(I), Count(I), 3个Unknown(H)
        params = struct.pack(
            "<B6sHHIIHHH",
            int(self.market),
            self.code,
            22, # Category 22
            1,  # Unknown
            self.start,
            self.count,
            0, 0, 0
        )
        return header + params

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
            # 这里的 i 是 uint32 原始字节，随后需用 _decode_volume 解码
            raw_data = struct.unpack("<Iiiiiiiii", body[pos:pos+36])
            
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
