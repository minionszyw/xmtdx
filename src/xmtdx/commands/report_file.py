"""大文件拉取命令（用于 base_info.zip, gpcw.txt 等）。"""

import struct

from .._binary import slice_bytes, unpack_from
from ..exceptions import TdxDecodeError
from .base import BaseCommand


class GetReportFileCmd(BaseCommand[bytes]):
    """分段获取服务器上的报表或基础信息文件。

    Args:
        filename: 远程文件名。
        start: 起始偏移量。
        length: 请求数据长度（建议 30000）。
    """

    def __init__(self, filename: str, start: int, length: int = 30000) -> None:
        self.filename = filename.encode("ascii")
        self.start = start
        self.length = length

    def build_request(self) -> bytes:
        # 使用与 GetBlockInfo 相同的格式：0x06B9
        header = bytes.fromhex("0c37186a00016e006e00b906")
        payload = struct.pack("<II", self.start, self.length)
        payload += (self.filename + b"\x00" * 100)[:100]
        return header + payload

    def parse_response(self, body: bytes) -> bytes:
        if len(body) < 4:
            return b""
        return body[4:]
