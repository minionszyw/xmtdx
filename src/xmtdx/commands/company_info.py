"""公司信息目录与内容命令。"""

import struct

from ..models.enums import Market
from ..models.finance import CompanyInfoCategory
from .base import BaseCommand


class GetCompanyInfoCategoryCmd(BaseCommand[list[CompanyInfoCategory]]):
    """获取公司信息文件目录（文件名列表 + 每段偏移/长度）。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c0f109b00010e000e00cf02".replace(" ", ""))
        return header + struct.pack("<H6sI", int(self.market), self.code, 0)

    def parse_response(self, body: bytes) -> list[CompanyInfoCategory]:
        if len(body) < 2:
            return []
        (num,) = struct.unpack_from("<H", body, 0)
        pos = 2
        results: list[CompanyInfoCategory] = []

        # 每条记录：64字节name + 80字节filename + 4字节start + 4字节length = 152字节
        _RECORD_SIZE = 152
        for _ in range(num):
            if pos + _RECORD_SIZE > len(body):
                break
            name_b, filename_b, start, length = struct.unpack_from("<64s80sII", body, pos)
            pos += _RECORD_SIZE

            def _decode(b: bytes) -> str:
                nul = b.find(b"\x00")
                raw = b[:nul] if nul != -1 else b
                return raw.decode("gbk", errors="replace")

            results.append(CompanyInfoCategory(
                filename=_decode(filename_b),
                start=start,
                length=length,
            ))

        return results


class GetCompanyInfoContentCmd(BaseCommand[str]):
    """按文件名、偏移、长度读取公司信息文本（GBK 编码）。"""

    def __init__(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.filename = filename.encode("gbk")
        self.offset = offset
        self.length = length

    def build_request(self) -> bytes:
        fname_padded = (self.filename + b"\x00" * 80)[:80]
        header = bytes.fromhex("0c07109c0001680068 00d002".replace(" ", ""))
        return header + struct.pack(
            "<H6sH80sIII",
            int(self.market), self.code, 0, fname_padded, self.offset, self.length, 0,
        )

    def parse_response(self, body: bytes) -> str:
        # 前12字节：10字节未知 + 2字节长度
        if len(body) < 12:
            return ""
        _, length = struct.unpack_from("<10sH", body, 0)
        content = body[12 : 12 + length]
        return content.decode("gbk", errors="replace")
