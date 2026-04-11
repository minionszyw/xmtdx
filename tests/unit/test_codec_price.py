"""get_price / put_price 单元测试，测试向量来自 pytdx 实际报文。"""

from xmtdx.codec.price import get_price, put_price


class TestGetPrice:
    def test_single_byte_zero(self):
        val, pos = get_price(b"\x00", 0)
        assert val == 0
        assert pos == 1

    def test_single_byte_positive(self):
        # 0x27 = 0b00100111 → bit7=0(stop), bit6=0(pos), low6=0x27=39
        val, pos = get_price(bytes([0x27]), 0)
        assert val == 39
        assert pos == 1

    def test_single_byte_negative(self):
        # bit6=1 → negative；low6=0x01 → -1
        val, pos = get_price(bytes([0x41]), 0)
        assert val == -1
        assert pos == 1

    def test_multi_byte_positive(self):
        # 0x8F 0x01: bit7=1(continue), low6=0x0F=15; 0x01: bit7=0(stop), 7bits=1
        # value = 15 | (1 << 6) = 15 + 64 = 79
        val, pos = get_price(bytes([0x8F, 0x01]), 0)
        assert val == 79
        assert pos == 2

    def test_pos_advances(self):
        data = bytes([0x05, 0x0A])
        val0, pos0 = get_price(data, 0)
        val1, pos1 = get_price(data, pos0)
        assert val0 == 5
        assert val1 == 10

    def test_roundtrip(self):
        for v in [0, 1, -1, 63, 64, -64, 1000, -1000, 99999, -99999]:
            encoded = put_price(v)
            decoded, _ = get_price(encoded, 0)
            assert decoded == v, f"roundtrip failed for {v}"


class TestPutPrice:
    def test_zero(self):
        assert put_price(0) == b"\x00"

    def test_small_positive(self):
        b = put_price(5)
        val, _ = get_price(b, 0)
        assert val == 5

    def test_small_negative(self):
        b = put_price(-5)
        val, _ = get_price(b, 0)
        assert val == -5

    def test_large_value(self):
        b = put_price(100000)
        val, _ = get_price(b, 0)
        assert val == 100000
