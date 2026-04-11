"""K 线数据模型"""

from dataclasses import dataclass, field


@dataclass
class SecurityBar:
    """单根 K 线（适用于 1m/5m/15m/30m/60m/日/周/月/季/年）"""

    open: float
    close: float
    high: float
    low: float
    vol: float    # 成交量（股）
    amount: float  # 成交额（元）

    year: int
    month: int
    day: int
    hour: int
    minute: int

    # 原始字节，供字段逆向分析使用
    _raw: bytes = field(default=b"", repr=False, compare=False)

    @property
    def datetime_str(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}"
