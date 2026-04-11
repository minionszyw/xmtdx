"""xmtdx — 通达信 TCP 协议 A 股行情数据客户端。

快速开始::

    from xmtdx import TdxClient, Market, KlineCategory

    with TdxClient("180.153.18.170") as c:
        count = c.get_security_count(Market.SH)
        bars  = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)

asyncio 版本::

    import asyncio
    from xmtdx import AsyncTdxClient, Market, KlineCategory

    async def main():
        async with AsyncTdxClient("180.153.18.170") as c:
            bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)

    asyncio.run(main())
"""

from .client import AsyncTdxClient, TdxClient
from .exceptions import TdxCommandError, TdxConnectionError, TdxDecodeError, TdxError
from .models import (
    XDXR_CATEGORY_NAMES,
    CompanyInfoCategory,
    FinanceInfo,
    KlineCategory,
    Market,
    MinuteBar,
    SecurityBar,
    SecurityInfo,
    SecurityQuote,
    TransactionRecord,
    XdxrRecord,
)
from .transport.sync import KNOWN_HOSTS, ping_all

__all__ = [
    # 客户端
    "TdxClient",
    "AsyncTdxClient",
    # 枚举
    "Market",
    "KlineCategory",
    # 数据模型
    "SecurityBar",
    "SecurityQuote",
    "SecurityInfo",
    "MinuteBar",
    "TransactionRecord",
    "XdxrRecord",
    "XDXR_CATEGORY_NAMES",
    "FinanceInfo",
    "CompanyInfoCategory",
    # 异常
    "TdxError",
    "TdxConnectionError",
    "TdxDecodeError",
    "TdxCommandError",
    # 工具
    "ping_all",
    "KNOWN_HOSTS",
]

__version__ = "0.1.0"
