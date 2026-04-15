"""市场代码与 K 线周期枚举"""

from enum import IntEnum


class Market(IntEnum):
    SZ = 0  # 深圳
    SH = 1  # 上海
    BJ = 2  # 北京


class KlineCategory(IntEnum):
    MIN_5 = 0
    MIN_15 = 1
    MIN_30 = 2
    MIN_60 = 3
    DAY = 4
    WEEK = 5
    MONTH = 6
    MIN_1 = 7
    MIN_3 = 8  # 通达信内部用，实际同 MIN_1
    YEAR = 9
    SEASON = 10
    YEAR_ALT = 11
