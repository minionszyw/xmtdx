"""板块信息获取命令（元数据获取与分片下载）。

板块文件（如 block_zs.dat）包含行业、概念、风格等 A 股分类信息。
"""

import struct

from .._binary import slice_bytes, unpack_from
from ..exceptions import TdxDecodeError
from .base import BaseCommand


class GetBlockInfoMetaCmd(BaseCommand[tuple[int, str]]):
    """获取板块文件的元数据（大小与 MD5 哈希）。

    Args:
        filename: 板块文件名，如 'block_zs.dat', 'block_gn.dat' 等。
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename.encode("ascii")

    def build_request(self) -> bytes:
        # 固定头 12 字节
        header = bytes.fromhex("0c39186900012a002a00c502")
        # Payload 为文件名
        payload = (self.filename + b"\x00" * 40)[:40]
        return header + payload

    def parse_response(self, body: bytes) -> tuple[int, str]:
        if len(body) < 38:
            raise TdxDecodeError(f"GetBlockInfoMeta 响应过短: {len(body)}")

        size, _, hash_b, _ = struct.unpack("<I1s32s1s", body[:38])
        return size, hash_b.decode("ascii").strip("\x00")


class GetBlockInfoCmd(BaseCommand[bytes]):
    """分段获取板块文件二进制内容。

    Args:
        filename: 板块文件名。
        start: 起始偏移量（字节）。
        length: 请求数据长度。
    """

    def __init__(self, filename: str, start: int, length: int) -> None:
        self.filename = filename.encode("ascii")
        self.start = start
        self.length = length

    def build_request(self) -> bytes:
        # 固定头 12 字节
        header = bytes.fromhex("0c37186a00016e006e00b906")
        payload = struct.pack("<II", self.start, self.length)
        payload += (self.filename + b"\x00" * 100)[:100]
        return header + payload

    def parse_response(self, body: bytes) -> bytes:
        if len(body) < 4:
            return b""
        return body[4:]
