"""日期时间解码单元测试。"""

import struct

from xmtdx.codec.datetime_ import get_datetime, get_datetime_day, get_datetime_minute, get_time


def _pack_minute(year: int, month: int, day: int, hour: int, minute: int) -> bytes:
    zipday = ((year - 2004) << 11) | (month * 100 + day)
    tminutes = hour * 60 + minute
    return struct.pack("<HH", zipday, tminutes)


def _pack_day(year: int, month: int, day: int) -> bytes:
    return struct.pack("<I", year * 10000 + month * 100 + day)


class TestGetDatetimeMinute:
    def test_basic(self):
        data = _pack_minute(2024, 4, 10, 14, 30)
        y, mo, d, h, mi, pos = get_datetime_minute(data, 0)
        assert (y, mo, d, h, mi) == (2024, 4, 10, 14, 30)
        assert pos == 4

    def test_open_time(self):
        data = _pack_minute(2026, 1, 5, 9, 30)
        y, mo, d, h, mi, pos = get_datetime_minute(data, 0)
        assert h == 9 and mi == 30

    def test_close_time(self):
        data = _pack_minute(2026, 1, 5, 15, 0)
        y, mo, d, h, mi, _ = get_datetime_minute(data, 0)
        assert h == 15 and mi == 0


class TestGetDatetimeDay:
    def test_basic(self):
        data = _pack_day(2026, 4, 10)
        y, mo, d, pos = get_datetime_day(data, 0)
        assert (y, mo, d) == (2026, 4, 10)
        assert pos == 4


class TestGetDatetime:
    def test_minute_category(self):
        data = _pack_minute(2026, 3, 15, 10, 0)
        for cat in (0, 1, 2, 3, 7, 8):
            y, mo, d, h, mi, _ = get_datetime(cat, data, 0)
            assert h == 10 and mi == 0

    def test_day_category(self):
        data = _pack_day(2026, 3, 15)
        for cat in (4, 5, 6, 9):
            y, mo, d, h, mi, _ = get_datetime(cat, data, 0)
            assert (y, mo, d) == (2026, 3, 15)
            assert h == 15 and mi == 0


class TestGetTime:
    def test_basic(self):
        data = struct.pack("<H", 14 * 60 + 30)  # 14:30
        h, mi, pos = get_time(data, 0)
        assert h == 14 and mi == 30
        assert pos == 2
