"""实时行情五档报价模型"""

from dataclasses import dataclass, field

from .enums import Market


@dataclass
class SecurityQuote:
    """单只股票实时五档行情。

    带 unknown_ 前缀的字段为协议中尚未明确含义的字段，保留以供逆向分析。
    _raw 为该股票记录的原始字节切片。
    """

    market: Market
    code: str

    # 价格
    price: float      # 现价
    pre_close: float  # 昨收
    open: float       # 今开
    high: float       # 最高
    low: float        # 最低

    # 量额
    vol: float        # 总成交量（手）
    cur_vol: float    # 当前成交量
    amount: float     # 成交额（元）
    s_vol: float      # 内盘（主动卖）
    b_vol: float      # 外盘（主动买）

    # 活跃度指标（含义来自社区逆向，仅供参考）
    active1: int
    active2: int

    # 买盘五档
    bid1: float
    bid_vol1: float
    bid2: float
    bid_vol2: float
    bid3: float
    bid_vol3: float
    bid4: float
    bid_vol4: float
    bid5: float
    bid_vol5: float

    # 卖盘五档
    ask1: float
    ask_vol1: float
    ask2: float
    ask_vol2: float
    ask3: float
    ask_vol3: float
    ask4: float
    ask_vol4: float
    ask5: float
    ask_vol5: float

    # 价格指标
    rise_speed: float  # 涨速（原 reversed_bytes9 / 100）
    limit_up: float | None    # 涨停价（业务规则计算）
    limit_down: float | None  # 跌停价（业务规则计算）

    # 未知字段：买卖量之后的两个变长整数（保留供进一步分析）
    unknown_2: int = field(default=0, repr=False)  # 未知变长整数 2
    unknown_3: int = field(default=0, repr=False)  # 未知变长整数 3

    # 未知字段：尾部四个变长整数
    unknown_5: int = field(default=0, repr=False)  # 原 reversed_bytes5
    unknown_6: int = field(default=0, repr=False)  # 原 reversed_bytes6
    unknown_7: int = field(default=0, repr=False)  # 原 reversed_bytes7
    unknown_8: int = field(default=0, repr=False)  # 原 reversed_bytes8

    # 服务器时间字符串（从 unknown_0 原始整数解析，格式 HH:MM:SS.mmm）
    server_time: str = field(default="", repr=True)

    # 原始字节（该股票记录切片）
    _raw: bytes = field(default=b"", repr=False, compare=False)
