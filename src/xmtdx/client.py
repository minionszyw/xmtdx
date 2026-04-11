"""高层行情 API：TdxClient（同步）和 AsyncTdxClient（asyncio）。"""

from types import TracebackType

from .commands.company_info import GetCompanyInfoCategoryCmd, GetCompanyInfoContentCmd
from .commands.finance_info import GetFinanceInfoCmd
from .commands.minute_time import GetHistoryMinuteTimeDataCmd, GetMinuteTimeDataCmd
from .commands.security_bars import GetIndexBarsCmd, GetSecurityBarsCmd
from .commands.security_count import GetSecurityCountCmd
from .commands.security_list import GetSecurityListCmd
from .commands.security_quotes import GetSecurityQuotesCmd
from .commands.transaction import GetHistoryTransactionDataCmd, GetTransactionDataCmd
from .commands.xdxr_info import GetXdxrInfoCmd
from .models.bar import SecurityBar
from .models.enums import KlineCategory, Market
from .models.finance import CompanyInfoCategory, FinanceInfo, XdxrRecord
from .models.quote import SecurityQuote
from .models.security import SecurityInfo
from .models.timeseries import MinuteBar, TransactionRecord
from .transport.async_ import AsyncTdxConnection
from .transport.sync import TdxConnection

_DEFAULT_HOST = "180.153.18.170"
_DEFAULT_PORT = 7709


# ============================================================
# 同步客户端
# ============================================================


class TdxClient:
    """同步通达信行情客户端。

    使用示例::

        with TdxClient("180.153.18.170") as c:
            bars = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
    ) -> None:
        self._conn = TdxConnection(host, port, timeout)

    def connect(self) -> None:
        self._conn.connect()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TdxClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    def get_security_count(self, market: Market) -> int:
        """获取市场证券总数。"""
        return self._conn.execute(GetSecurityCountCmd(market))

    def get_security_list(self, market: Market, start: int) -> list[SecurityInfo]:
        """获取证券列表（每页约1000条，按 start 分页）。"""
        return self._conn.execute(GetSecurityListCmd(market, start))

    def get_security_quotes(
        self, stocks: list[tuple[Market, str]]
    ) -> list[SecurityQuote]:
        """批量获取实时五档行情（最多80只/次）。"""
        return self._conn.execute(GetSecurityQuotesCmd(stocks))

    # ------------------------------------------------------------------ #
    # K 线
    # ------------------------------------------------------------------ #

    def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        """获取 K 线数据（最多800条/次，按 start 分页）。"""
        return self._conn.execute(GetSecurityBarsCmd(market, code, category, start, count))

    def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        """获取指数 K 线数据。"""
        return self._conn.execute(GetIndexBarsCmd(market, code, category, start, count))

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        """获取今日分时数据（240条）。"""
        return self._conn.execute(GetMinuteTimeDataCmd(market, code))

    def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        """获取历史某日分时数据（date: YYYYMMDD）。"""
        return self._conn.execute(GetHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        """获取当日逐笔成交（分页）。"""
        return self._conn.execute(GetTransactionDataCmd(market, code, start, count))

    def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        """获取历史逐笔成交（date: YYYYMMDD，分页）。"""
        return self._conn.execute(
            GetHistoryTransactionDataCmd(market, code, date, start, count)
        )

    # ------------------------------------------------------------------ #
    # 财务 / 公司
    # ------------------------------------------------------------------ #

    def get_xdxr_info(self, market: Market, code: str) -> list[XdxrRecord]:
        """获取除权除息历史记录。"""
        return self._conn.execute(GetXdxrInfoCmd(market, code))

    def get_finance_info(self, market: Market, code: str) -> FinanceInfo:
        """获取最新财务数据。"""
        return self._conn.execute(GetFinanceInfoCmd(market, code))

    def get_company_info_category(
        self, market: Market, code: str
    ) -> list[CompanyInfoCategory]:
        """获取公司信息文件目录。"""
        return self._conn.execute(GetCompanyInfoCategoryCmd(market, code))

    def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        """读取公司信息文本。"""
        return self._conn.execute(
            GetCompanyInfoContentCmd(market, code, filename, offset, length)
        )


# ============================================================
# 异步客户端
# ============================================================


class AsyncTdxClient:
    """异步通达信行情客户端（asyncio）。

    使用示例::

        async with AsyncTdxClient("180.153.18.170") as c:
            bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
    ) -> None:
        self._conn = AsyncTdxConnection(host, port, timeout)

    async def connect(self) -> None:
        await self._conn.connect()

    async def close(self) -> None:
        await self._conn.close()

    async def __aenter__(self) -> "AsyncTdxClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def get_security_count(self, market: Market) -> int:
        return await self._conn.execute(GetSecurityCountCmd(market))

    async def get_security_list(self, market: Market, start: int) -> list[SecurityInfo]:
        return await self._conn.execute(GetSecurityListCmd(market, start))

    async def get_security_quotes(
        self, stocks: list[tuple[Market, str]]
    ) -> list[SecurityQuote]:
        return await self._conn.execute(GetSecurityQuotesCmd(stocks))

    async def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        return await self._conn.execute(GetSecurityBarsCmd(market, code, category, start, count))

    async def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        return await self._conn.execute(GetIndexBarsCmd(market, code, category, start, count))

    async def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        return await self._conn.execute(GetMinuteTimeDataCmd(market, code))

    async def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        return await self._conn.execute(GetHistoryMinuteTimeDataCmd(market, code, date))

    async def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        return await self._conn.execute(GetTransactionDataCmd(market, code, start, count))

    async def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        return await self._conn.execute(
            GetHistoryTransactionDataCmd(market, code, date, start, count)
        )

    async def get_xdxr_info(self, market: Market, code: str) -> list[XdxrRecord]:
        return await self._conn.execute(GetXdxrInfoCmd(market, code))

    async def get_finance_info(self, market: Market, code: str) -> FinanceInfo:
        return await self._conn.execute(GetFinanceInfoCmd(market, code))

    async def get_company_info_category(
        self, market: Market, code: str
    ) -> list[CompanyInfoCategory]:
        return await self._conn.execute(GetCompanyInfoCategoryCmd(market, code))

    async def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        return await self._conn.execute(
            GetCompanyInfoContentCmd(market, code, filename, offset, length)
        )
