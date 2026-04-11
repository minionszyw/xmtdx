"""日期时间解码（通达信 TCP 两种格式）。

分钟级（category < 4 或 == 7/8）：4 字节 = 2 字节压缩日期 + 2 字节分钟数
  zipday: year=(>>11)+2004, month=(% 2048)//100, day=(% 2048)%100
  tminutes: hour=//60, minute=%60

日线及以上（其余 category）：4 字节 YYYYMMDD 整数
"""


from .._binary import unpack_from


def get_datetime_minute(
    data: bytes | bytearray, pos: int
) -> tuple[int, int, int, int, int, int]:
    """解析分钟级时间戳（4 字节）。

    Returns:
        (year, month, day, hour, minute, new_pos)
    """
    zipday, tminutes = unpack_from("<HH", data, pos, "minute datetime")
    year = (zipday >> 11) + 2004
    month = (zipday % 2048) // 100
    day = (zipday % 2048) % 100
    hour = tminutes // 60
    minute = tminutes % 60
    return year, month, day, hour, minute, pos + 4


def get_datetime_day(
    data: bytes | bytearray, pos: int
) -> tuple[int, int, int, int]:
    """解析日期（4 字节 YYYYMMDD）。

    Returns:
        (year, month, day, new_pos)
    """
    (zipday,) = unpack_from("<I", data, pos, "day datetime")
    year = zipday // 10000
    month = (zipday % 10000) // 100
    day = zipday % 100
    return year, month, day, pos + 4


def get_datetime(
    category: int, data: bytes | bytearray, pos: int
) -> tuple[int, int, int, int, int, int]:
    """根据 KlineCategory 选择解析格式。

    Returns:
        (year, month, day, hour, minute, new_pos)
        日线及以上时 hour=15, minute=0（收盘时间，与 pytdx 保持一致）
    """
    if category < 4 or category in (7, 8):
        return get_datetime_minute(data, pos)
    else:
        year, month, day, new_pos = get_datetime_day(data, pos)
        return year, month, day, 15, 0, new_pos


def get_time(data: bytes | bytearray, pos: int) -> tuple[int, int, int]:
    """解析 2 字节时间（分钟数）。

    Returns:
        (hour, minute, new_pos)
    """
    (tminutes,) = unpack_from("<H", data, pos, "trade time")
    return tminutes // 60, tminutes % 60, pos + 2
