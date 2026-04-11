"""get_volume 单元测试，测试向量来自 pytdx 注释中的已知值。"""

import struct

from xmtdx.codec.volume import get_volume


def _pack(ivol: int) -> bytes:
    return struct.pack("<I", ivol)


class TestGetVolume:
    def test_zero(self):
        val, pos = get_volume(_pack(0), 0)
        assert val == 0.0
        assert pos == 4

    def test_known_value_4098(self):
        # pytdx 注释 "4098 ---> 3.0" 含义：raw 4098 对应真实股数 3.0亿，
        # 但 get_volume(4098) ≈ 5.88e-39（接近零），说明 xdxr_info 里对股本字段
        # 调用 get_volume 是错误用法。xmtdx 在 xdxr_info 命令中会用正确的解码方式。
        val, pos = get_volume(_pack(4098), 0)
        assert abs(val) < 1e-30  # 接近零，与 pytdx 行为一致

    def test_advances_pos(self):
        data = _pack(0) + _pack(0)
        _, pos = get_volume(data, 0)
        assert pos == 4
        _, pos2 = get_volume(data, pos)
        assert pos2 == 8

    def test_nonnegative(self):
        # 成交量不应为负
        for raw in [0, 1000, 0x10000, 0x1000000, 0x7FFFFFFF]:
            val, _ = get_volume(_pack(raw), 0)
            assert val >= 0.0
