"""响应帧头解析与解压单元测试。"""

import struct
import zlib

from xmtdx.codec.frame import HEADER_SIZE, decompress_body, parse_header


def _make_header(zipsize: int, unzipsize: int) -> bytes:
    return struct.pack("<IIIHH", 0, 0, 0, zipsize, unzipsize)


class TestParseHeader:
    def test_uncompressed(self):
        h = parse_header(_make_header(100, 100))
        assert h.zipsize == 100
        assert h.unzipsize == 100

    def test_compressed(self):
        h = parse_header(_make_header(50, 200))
        assert h.zipsize == 50
        assert h.unzipsize == 200

    def test_header_size(self):
        assert HEADER_SIZE == 16


class TestDecompressBody:
    def test_no_compression(self):
        h = parse_header(_make_header(5, 5))
        body = b"hello"
        assert decompress_body(h, body) == b"hello"

    def test_zlib_decompression(self):
        original = b"hello world" * 10
        compressed = zlib.compress(original)
        h = parse_header(_make_header(len(compressed), len(original)))
        result = decompress_body(h, compressed)
        assert result == original
