"""高层行情 API：TdxClient（同步）和 AsyncTdxClient（asyncio）。"""

import asyncio
from types import TracebackType
from typing import TypeVar

from .codec.block import parse_block_dat
from .codec.industry import parse_tdxhy_cfg
from .commands.base import BaseCommand
from .commands.block_info import GetBlockInfoCmd, GetBlockInfoMetaCmd
from .commands.company_info import GetCompanyInfoCategoryCmd, GetCompanyInfoContentCmd
from .commands.finance_info import GetFinanceInfoCmd
from .commands.fund_flow import GetHistoryFundFlowCmd
from .commands.minute_time import GetHistoryMinuteTimeDataCmd, GetMinuteTimeDataCmd
from .commands.report_file import GetReportFileCmd
from .commands.security_bars import GetIndexBarsCmd, GetSecurityBarsCmd
from .commands.security_count import GetSecurityCountCmd
from .commands.security_list import GetSecurityListCmd
from .commands.security_quotes import GetSecurityQuotesCmd
from .commands.transaction import GetHistoryTransactionDataCmd, GetTransactionDataCmd
from .commands.xdxr_info import GetXdxrInfoCmd
from .exceptions import TdxConnectionError
from .models.bar import SecurityBar
from .models.enums import KlineCategory, Market
from .models.finance import CompanyInfoCategory, FinanceInfo, TdxBlock, XdxrRecord
from .models.quote import SecurityQuote
from .models.security import SecurityInfo
from .models.stats import FundFlow, HistoricalFundFlow, MarketStat
from .models.timeseries import MinuteBar, TransactionRecord
from .transport.async_ import AsyncTdxConnection
from .transport.sync import KNOWN_HOSTS, TdxConnection, ping_all

_DEFAULT_PORT = 7709
_T = TypeVar("_T")


# ============================================================
# 同步客户端
# ============================================================


class TdxClient:
    """同步通达信行情客户端，支持 IP 优选与断线自动重连。

    使用示例::

        # 单台服务器
        with TdxClient("180.153.18.170") as c:
            bars = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)

        # 自动从候选列表中选延迟最低的服务器
        with TdxClient.from_best_host() as c:
            count = c.get_security_count(Market.SH)
    """

    def __init__(
        self,
        host: str = KNOWN_HOSTS[0],
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._conn = TdxConnection(host, port, timeout)

    # ------------------------------------------------------------------ #
    # 工厂方法：自动优选最低延迟服务器
    # ------------------------------------------------------------------ #

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
    ) -> "TdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟的建立连接。

        若所有服务器均不可达，回退到 hosts[0]。
        """
        ranked = ping_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        return cls(best, port, timeout, auto_reconnect)

    @staticmethod
    def ping_all(
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        return ping_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

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
    # 内部执行：含自动重连
    # ------------------------------------------------------------------ #

    def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        """执行命令；断线时尝试重连一次再重试（若 auto_reconnect=True）。"""
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            # 重连后重试一次
            self._conn.close()
            self._conn = TdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            return self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    def get_security_count(self, market: Market) -> int:
        """获取市场证券总数。"""
        return self._execute(GetSecurityCountCmd(market))

    def get_security_list(self, market: Market, start: int) -> list[SecurityInfo]:
        """获取证券列表（每页约1000条，按 start 分页）。"""
        return self._execute(GetSecurityListCmd(market, start))

    def get_security_list_all(self) -> list[SecurityInfo]:
        """获取沪深 A 股完整证券列表，并自动挂载行业信息。

        注意：
            `Market.BJ` 的证券列表请求长期存在服务器超时问题，当前版本暂不纳入此方法。
            若需 BJ 名单，应改由 `base_info.zip` 等文件离线解析获得。
        """
        # 1. 尝试获取行业配置
        industry_map = {}
        try:
            cfg_data = self.get_report_file("tdxhy.cfg")
            if cfg_data:
                industry_map = parse_tdxhy_cfg(cfg_data)
        except Exception:
            pass

        all_stocks: list[SecurityInfo] = []
        # 注意：Market.BJ 证券列表请求常年超时，短期降级为仅 SH/SZ；
        # BJ 列表需解析 base_info.zip 获得（待实现）。
        for market in [Market.SH, Market.SZ]:
            count = self.get_security_count(market)
            for start in range(0, count, 1000):
                stocks = self.get_security_list(market, start)
                for s in stocks:
                    # 精确 A 股过滤规则
                    is_a_share = False
                    if market == Market.SH:
                        # 沪市 A 股：60xxxx, 68xxxx
                        if s.code.startswith(("60", "68")):
                            is_a_share = True
                    elif market == Market.SZ:
                        # 深市 A 股：00xxxx, 30xxxx
                        if s.code.startswith(("00", "30")):
                            is_a_share = True
                    
                    if is_a_share:
                        # 挂载行业信息
                        if s.code in industry_map:
                            s.industry_tdx, s.industry_sw = industry_map[s.code]
                        all_stocks.append(s)
        return all_stocks

    def get_security_quotes(
        self, stocks: list[tuple[Market, str]]
    ) -> list[SecurityQuote]:
        """批量获取实时五档行情（最多80只/次）。"""
        return self._execute(GetSecurityQuotesCmd(stocks))

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
        return self._execute(GetSecurityBarsCmd(market, code, category, start, count))

    def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        """获取指数 K 线数据。"""
        return self._execute(GetIndexBarsCmd(market, code, category, start, count))

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        """获取今日分时数据（240条）。"""
        return self._execute(GetMinuteTimeDataCmd(market, code))

    def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        """获取历史某日分时数据（date: YYYYMMDD）。"""
        return self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        """获取当日逐笔成交（分页）。"""
        return self._execute(GetTransactionDataCmd(market, code, start, count))

    def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        """获取历史逐笔成交（date: YYYYMMDD，分页）。"""
        return self._execute(
            GetHistoryTransactionDataCmd(market, code, date, start, count)
        )

    # ------------------------------------------------------------------ #
    # 财务 / 公司
    # ------------------------------------------------------------------ #

    def get_xdxr_info(self, market: Market, code: str) -> list[XdxrRecord]:
        """获取除权除息历史记录。"""
        return self._execute(GetXdxrInfoCmd(market, code))

    def get_finance_info(self, market: Market, code: str) -> FinanceInfo:
        """获取最新财务数据。"""
        return self._execute(GetFinanceInfoCmd(market, code))

    def get_company_info_category(
        self, market: Market, code: str
    ) -> list[CompanyInfoCategory]:
        """获取公司信息文件目录。"""
        return self._execute(GetCompanyInfoCategoryCmd(market, code))

    def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        """读取公司信息文本。"""
        return self._execute(
            GetCompanyInfoContentCmd(market, code, filename, offset, length)
        )

    def get_block_info(self, filename: str) -> list[TdxBlock]:
        """获取并解析板块文件（行业、概念、风格等）。

        常用文件名：
          'block_zs.dat'  - 行业/指数板块
          'block_gn.dat'  - 概念板块
          'block_fg.dat'  - 风格板块
        """
        size, _hash = self._execute(GetBlockInfoMetaCmd(filename))
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while pos < size:
            chunk = self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
        return parse_block_dat(bytes(full_data), filename)

    def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件（如 'base_info.zip'）。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while True:
            chunk = self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
        return bytes(full_data)

    def get_market_stat(self) -> MarketStat:
        """获取 A 股全市场涨跌统计概况（基于 880005 行情统计）。

        注意：
            `suspended_count` 是 `total - up - down - neutral` 的残差估算值，
            用于保证计数守恒，不应视为协议已明确验证的停牌字段。
        """
        # 通达信中 880005 是全市场行情统计代码
        quotes = self.get_security_quotes([(Market.SH, "880005")])
        if not quotes:
            raise RuntimeError("无法获取市场统计数据")
        q = quotes[0]
        up = int(q.price)
        down = int(q.pre_close)
        neutral = int(q.low)
        total = int(q.high)
        return MarketStat(
            up_count=up,
            down_count=down,
            neutral_count=neutral,
            suspended_count=max(0, total - up - down - neutral),
            total_count=total,
            total_amount=q.amount,
            total_volume=q.vol,
        )

    def get_fund_flow(self, market: Market, code: str) -> FundFlow:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        # 1. 分页拉取当日分笔并去重
        all_recs: list[TransactionRecord] = []
        seen_sig = set()
        seen_page_sigs = set()
        start = 0
        
        while start < 10000:
            recs = self.get_transaction_data(market, code, start, 2000)
            if not recs:
                break
            
            # 页签名判断：首尾记录组合
            page_sig = (
                (
                    recs[0].hour, recs[0].minute, recs[0].price,
                    recs[0].vol, recs[0].buyorsell, recs[0].unknown_last
                ),
                (
                    recs[-1].hour, recs[-1].minute, recs[-1].price,
                    recs[-1].vol, recs[-1].buyorsell, recs[-1].unknown_last
                ),
            )
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            new_count = 0
            for r in recs:
                sig = (r.hour, r.minute, r.price, r.vol, r.buyorsell, r.unknown_last)
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    all_recs.append(r)
                    new_count += 1
            
            if new_count == 0:
                break
                
            start += len(recs)
            if len(recs) < 100:
                break
        
        # 2. 统计逻辑
        # A 股标准：超大(>100w), 大单(20w-100w), 中单(4w-20w), 小单(<4w)
        stats = {
            "super_in": 0.0, "large_in": 0.0, "medium_in": 0.0, "small_in": 0.0,
            "super_out": 0.0, "large_out": 0.0, "medium_out": 0.0, "small_out": 0.0,
        }
        
        for r in all_recs:
            amount = r.price * r.vol * 100.0 # A股 1手=100股
            direction = "in" if r.buyorsell == 0 else "out" if r.buyorsell == 1 else None
            if not direction:
                continue
                
            if amount >= 1000000:
                stats[f"super_{direction}"] += amount
            elif amount >= 200000:
                stats[f"large_{direction}"] += amount
            elif amount >= 40000:
                stats[f"medium_{direction}"] += amount
            else:
                stats[f"small_{direction}"] += amount
                
        return FundFlow(**stats)

    def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> list[HistoricalFundFlow]:
        """获取个股历史日线资金流向序列（Category 22）。

        [EXPERIMENTAL] 当前多台公开主机对该请求仍可能返回空列表。
        """
        return self._execute(GetHistoryFundFlowCmd(market, code, start, count))


# ============================================================
# 异步客户端
# ============================================================


class AsyncTdxClient:
    """异步通达信行情客户端（asyncio）。

    使用示例::

        async with AsyncTdxClient("180.153.18.170") as c:
            bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)

    注意：
        单个 AsyncTdxClient 仅维护一条 TCP 连接；并发调用会在连接内串行执行。
    """

    def __init__(
        self,
        host: str = KNOWN_HOSTS[0],
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncTdxConnection(host, port, timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> "AsyncTdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟的建立连接。"""
        ranked = ping_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        return ping_all(hosts, port, timeout)

    async def connect(self) -> None:
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
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

    def _start_heartbeat(self) -> None:
        """启动后台心跳任务。"""
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """停止并清理心跳任务。"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """心跳循环：定期发送轻量级请求保活。"""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                # 使用 get_security_count 作为心跳包
                await self.get_security_count(Market.SH)
            except asyncio.CancelledError:
                break
            except Exception:
                # 心跳失败通常意味着连接已断开
                # 下一次正常的业务请求或下一次心跳会通过 _execute 触发重连
                pass

    async def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        """执行命令；断线时尝试重连一次再重试（若 auto_reconnect=True）。"""
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                await self._conn.close()
                self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
                await self._conn.connect()
                return await self._conn.execute(cmd)

    async def get_security_count(self, market: Market) -> int:
        return await self._execute(GetSecurityCountCmd(market))

    async def get_security_list(self, market: Market, start: int) -> list[SecurityInfo]:
        return await self._execute(GetSecurityListCmd(market, start))

    async def get_security_list_all(self) -> list[SecurityInfo]:
        """获取沪深 A 股完整证券列表，并自动挂载行业信息。

        注意：
            `Market.BJ` 的证券列表请求长期存在服务器超时问题，当前版本暂不纳入此方法。
            若需 BJ 名单，应改由 `base_info.zip` 等文件离线解析获得。
        """
        industry_map = {}
        try:
            cfg_data = await self.get_report_file("tdxhy.cfg")
            if cfg_data:
                industry_map = parse_tdxhy_cfg(cfg_data)
        except Exception:
            pass

        all_stocks: list[SecurityInfo] = []
        # 注意：Market.BJ 证券列表请求常年超时，短期降级为仅 SH/SZ；
        # BJ 列表需解析 base_info.zip 获得（待实现）。
        for market in [Market.SH, Market.SZ]:
            count = await self.get_security_count(market)
            for start in range(0, count, 1000):
                stocks = await self.get_security_list(market, start)
                for s in stocks:
                    is_a_share = False
                    if market == Market.SH:
                        if s.code.startswith(("60", "68")):
                            is_a_share = True
                    elif market == Market.SZ:
                        if s.code.startswith(("00", "30")):
                            is_a_share = True
                    
                    if is_a_share:
                        if s.code in industry_map:
                            s.industry_tdx, s.industry_sw = industry_map[s.code]
                        all_stocks.append(s)
        return all_stocks

    async def get_security_quotes(
        self, stocks: list[tuple[Market, str]]
    ) -> list[SecurityQuote]:
        return await self._execute(GetSecurityQuotesCmd(stocks))

    async def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        return await self._execute(
            GetSecurityBarsCmd(market, code, category, start, count)
        )

    async def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        return await self._execute(GetIndexBarsCmd(market, code, category, start, count))

    async def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        return await self._execute(GetMinuteTimeDataCmd(market, code))

    async def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        return await self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))

    async def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        return await self._execute(GetTransactionDataCmd(market, code, start, count))

    async def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> list[TransactionRecord]:
        return await self._execute(
            GetHistoryTransactionDataCmd(market, code, date, start, count)
        )

    async def get_xdxr_info(self, market: Market, code: str) -> list[XdxrRecord]:
        return await self._execute(GetXdxrInfoCmd(market, code))

    async def get_finance_info(self, market: Market, code: str) -> FinanceInfo:
        return await self._execute(GetFinanceInfoCmd(market, code))

    async def get_company_info_category(
        self, market: Market, code: str
    ) -> list[CompanyInfoCategory]:
        return await self._execute(GetCompanyInfoCategoryCmd(market, code))

    async def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        return await self._execute(
            GetCompanyInfoContentCmd(market, code, filename, offset, length)
        )

    async def get_block_info(self, filename: str) -> list[TdxBlock]:
        """获取并解析板块文件（行业、概念、风格等）。"""
        size, _hash = await self._execute(GetBlockInfoMetaCmd(filename))
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while pos < size:
            chunk = await self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
        return parse_block_dat(bytes(full_data), filename)

    async def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while True:
            chunk = await self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
        return bytes(full_data)

    async def get_market_stat(self) -> MarketStat:
        """获取 A 股全市场涨跌统计概况（基于 880005 行情统计）。

        注意：
            `suspended_count` 是 `total - up - down - neutral` 的残差估算值，
            用于保证计数守恒，不应视为协议已明确验证的停牌字段。
        """
        # 通达信中 880005 是全市场行情统计代码
        quotes = await self.get_security_quotes([(Market.SH, "880005")])
        if not quotes:
            raise RuntimeError("无法获取市场统计数据")
        q = quotes[0]
        up = int(q.price)
        down = int(q.pre_close)
        neutral = int(q.low)
        total = int(q.high)
        return MarketStat(
            up_count=up,
            down_count=down,
            neutral_count=neutral,
            suspended_count=max(0, total - up - down - neutral),
            total_count=total,
            total_amount=q.amount,
            total_volume=q.vol,
        )

    async def get_fund_flow(self, market: Market, code: str) -> FundFlow:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        # 1. 分页拉取当日分笔并去重
        all_recs: list[TransactionRecord] = []
        seen_sig = set()
        seen_page_sigs = set()
        start = 0
        
        while start < 10000:
            recs = await self.get_transaction_data(market, code, start, 2000)
            if not recs:
                break
            
            # 页签名判断：首尾记录组合
            page_sig = (
                (
                    recs[0].hour, recs[0].minute, recs[0].price,
                    recs[0].vol, recs[0].buyorsell, recs[0].unknown_last
                ),
                (
                    recs[-1].hour, recs[-1].minute, recs[-1].price,
                    recs[-1].vol, recs[-1].buyorsell, recs[-1].unknown_last
                ),
            )
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            new_count = 0
            for r in recs:
                sig = (r.hour, r.minute, r.price, r.vol, r.buyorsell, r.unknown_last)
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    all_recs.append(r)
                    new_count += 1
            
            if new_count == 0:
                break
                
            start += len(recs)
            if len(recs) < 100:
                break
        
        stats = {
            "super_in": 0.0, "large_in": 0.0, "medium_in": 0.0, "small_in": 0.0,
            "super_out": 0.0, "large_out": 0.0, "medium_out": 0.0, "small_out": 0.0,
        }
        for r in all_recs:
            amount = r.price * r.vol * 100.0
            direction = "in" if r.buyorsell == 0 else "out" if r.buyorsell == 1 else None
            if not direction:
                continue
            if amount >= 1000000:
                stats[f"super_{direction}"] += amount
            elif amount >= 200000:
                stats[f"large_{direction}"] += amount
            elif amount >= 40000:
                stats[f"medium_{direction}"] += amount
            else:
                stats[f"small_{direction}"] += amount
        return FundFlow(**stats)

    async def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> list[HistoricalFundFlow]:
        """获取个股历史日线资金流向序列（Category 22）。

        [EXPERIMENTAL] 当前多台公开主机对该请求仍可能返回空列表。
        """
        return await self._execute(GetHistoryFundFlowCmd(market, code, start, count))
