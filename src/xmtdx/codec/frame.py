"""响应帧头解析与 zlib 解压。

响应帧格式（16 字节固定头 + body）：
  struct "<IIIHH"
  偏移  0: I (4字节) — 未知
  偏移  4: I (4字节) — 未知
  偏移  8: I (4字节) — 未知
  偏移 12: H (2字节) — zipsize（body 实际长度）
  偏移 14: H (2字节) — unzipsize（解压后长度；等于 zipsize 表示未压缩）
"""

import struct
import zlib
from dataclasses import dataclass

HEADER_SIZE: int = 16
_HEADER_FMT = "<IIIHH"


@dataclass(frozen=True)
class FrameHeader:
    unknown_0: int
    unknown_1: int
    unknown_2: int
    zipsize: int
    unzipsize: int


def parse_header(buf: bytes) -> FrameHeader:
    """解析 16 字节响应帧头。"""
    u0, u1, u2, zipsize, unzipsize = struct.unpack_from(_HEADER_FMT, buf)
    return FrameHeader(u0, u1, u2, zipsize, unzipsize)


def decompress_body(header: FrameHeader, raw_body: bytes) -> bytes:
    """按需 zlib 解压 body。

    zipsize == unzipsize 时直接返回原始字节；否则 zlib 解压。
    """
    if header.zipsize == header.unzipsize:
        return raw_body
    return zlib.decompress(raw_body)
