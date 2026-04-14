"""证券基本信息模型"""

from dataclasses import dataclass, field

from .enums import Market


@dataclass
class SecurityInfo:
    """证券列表条目（来自 get_security_list）"""

    market: Market
    code: str
    name: str          # 股票名称（GBK 解码，截断字节用 replacement char 替代）
    volunit: int       # 成交量单位（手 = volunit 股）
    decimal_point: int  # 价格小数位数
    pre_close: float   # 昨收价（已修复 pytdx Bug #3：改用正确价格解码）

    # 扩展字段（通过 get_security_list_all 关联 tdxhy.cfg 获得）
    industry_tdx: str = ""  # 通达信行业代码 (如 T1001)
    industry_sw: str = ""   # 申万行业代码 (如 X500102)

    _raw: bytes = field(default=b"", repr=False, compare=False)
