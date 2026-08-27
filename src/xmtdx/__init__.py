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
from .dataframe import to_dataframe
from .exceptions import (
    TdxCommandError,
    TdxConnectionError,
    TdxDecodeError,
    TdxError,
    TdxResponseError,
)
from .models import (
    XDXR_CATEGORY_NAMES,
    CompanyInfoCategory,
    FinanceInfo,
    IndexBar,
    KlineCategory,
    Market,
    MinuteBar,
    SecurityBar,
    SecurityInfo,
    SecurityQuote,
    TransactionRecord,
    XdxrRecord,
)
from .models.finance import TdxBlock
from .models.stats import FundFlow, HistoricalFundFlow, MarketStat
from .transport.async_ import ping_all_async
from .transport.capture import CapturedResponse
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
    "IndexBar",
    "SecurityQuote",
    "SecurityInfo",
    "MinuteBar",
    "TransactionRecord",
    "XdxrRecord",
    "XDXR_CATEGORY_NAMES",
    "FinanceInfo",
    "CompanyInfoCategory",
    "TdxBlock",
    "MarketStat",
    "FundFlow",
    "HistoricalFundFlow",
    # 异常
    "TdxError",
    "TdxConnectionError",
    "TdxDecodeError",
    "TdxResponseError",
    "TdxCommandError",
    # 工具
    "ping_all",
    "ping_all_async",
    "KNOWN_HOSTS",
    "to_dataframe",
    "CapturedResponse",
]

__version__ = "0.2.1"
