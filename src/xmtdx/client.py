"""高层行情 API：TdxClient（同步）和 AsyncTdxClient（asyncio）。"""

import asyncio
import hashlib
import math
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from types import TracebackType
from typing import TypeVar
from zoneinfo import ZoneInfo

from .codec.block import parse_block_dat
from .codec.industry import parse_tdxhy_cfg
from .codec.price_rules import compute_price_limits, get_no_limit_window_days
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
from .exceptions import TdxConnectionError, TdxDecodeError, TdxResponseError
from .models.bar import IndexBar, SecurityBar
from .models.enums import KlineCategory, Market
from .models.finance import CompanyInfoCategory, FinanceInfo, TdxBlock, XdxrRecord
from .models.quote import SecurityQuote
from .models.security import SecurityInfo
from .models.stats import FundFlow, HistoricalFundFlow, MarketStat
from .models.timeseries import MinuteBar, TransactionRecord
from .transport.async_ import AsyncTdxConnection, ping_all_async
from .transport.sync import KNOWN_HOSTS, TdxConnection, ping_all
from .validation import validate_date

_DEFAULT_PORT = 7709
_DEFAULT_TIMEOUT = 5.0
_T = TypeVar("_T")
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _today_in_shanghai() -> int:
    return int(datetime.now(_SHANGHAI_TZ).strftime("%Y%m%d"))


def _now_in_shanghai() -> datetime:
    return datetime.now(_SHANGHAI_TZ)


def _record_signature(
    record: TransactionRecord,
) -> tuple[int, int, float, int, int, int, int | None]:
    return (
        record.hour,
        record.minute,
        record.price,
        record.vol,
        record.buyorsell,
        record.unknown_last,
        record.num_orders,
    )


def _page_signature(
    records: list[TransactionRecord],
) -> tuple[tuple[int, int, float, int, int, int, int | None], ...]:
    return tuple(_record_signature(record) for record in records)


def _boundary_overlap(
    existing: list[TransactionRecord], new_page: list[TransactionRecord]
) -> int:
    """返回现有尾部与新页头部完全相同的最大连续记录数。"""
    limit = min(len(existing), len(new_page))
    existing_signatures = [_record_signature(record) for record in existing[-limit:]]
    new_signatures = [_record_signature(record) for record in new_page[:limit]]
    for size in range(limit, 0, -1):
        if existing_signatures[-size:] == new_signatures[:size]:
            return size
    return 0


def _classify_fund_flow(records: list[TransactionRecord]) -> FundFlow:
    stats = {
        "super_in": 0.0,
        "large_in": 0.0,
        "medium_in": 0.0,
        "small_in": 0.0,
        "super_out": 0.0,
        "large_out": 0.0,
        "medium_out": 0.0,
        "small_out": 0.0,
    }

    for record in records:
        amount = record.price * record.vol * 100.0
        direction = (
            "in" if record.buyorsell == 0 else "out" if record.buyorsell == 1 else None
        )
        if not direction:
            continue

        if amount > 1_000_000:
            stats[f"super_{direction}"] += amount
        elif amount > 200_000:
            stats[f"large_{direction}"] += amount
        elif amount > 40_000:
            stats[f"medium_{direction}"] += amount
        else:
            stats[f"small_{direction}"] += amount

    return FundFlow(**stats)


def _date_from_bar(bar: SecurityBar) -> int:
    return bar.year * 10000 + bar.month * 100 + bar.day


def _unique_hosts(primary: str, fallbacks: Sequence[str]) -> list[str]:
    hosts: list[str] = []
    for host in (primary, *fallbacks):
        if host and host not in hosts:
            hosts.append(host)
    if not hosts:
        raise ValueError("至少需要一个行情服务器")
    return hosts


def _looks_like_index(market: Market, code: str) -> bool:
    if market == Market.SH:
        return code.startswith(("000", "880", "881", "882", "883", "884", "885", "999"))
    if market == Market.SZ:
        return code.startswith(("395", "399"))
    return False


def _validate_bars(bars: Sequence[SecurityBar], context: str) -> None:
    for index, bar in enumerate(bars):
        values = (bar.open, bar.close, bar.high, bar.low, bar.vol, bar.amount)
        if not all(math.isfinite(value) for value in values):
            raise TdxResponseError(f"{context}[{index}] 包含非有限数值")
        try:
            datetime(bar.year, bar.month, bar.day)
        except ValueError:
            raise TdxResponseError(
                f"{context}[{index}] 日期非法: {bar.year}-{bar.month}-{bar.day}"
            ) from None
        if not 1990 <= bar.year <= 2100:
            raise TdxResponseError(
                f"{context}[{index}] 日期非法: {bar.year}-{bar.month}-{bar.day}"
            )
        if bar.vol < 0 or bar.amount < 0:
            raise TdxResponseError(f"{context}[{index}] 成交量或成交额为负")
        if bar.high + 0.001 < max(bar.open, bar.close, bar.low):
            raise TdxResponseError(f"{context}[{index}] 最高价关系非法")
        if bar.low - 0.001 > min(bar.open, bar.close, bar.high):
            raise TdxResponseError(f"{context}[{index}] 最低价关系非法")


def _validate_minute_bars(
    bars: Sequence[MinuteBar], context: str, reference_price: float | None = None
) -> None:
    for index, bar in enumerate(bars):
        if not math.isfinite(bar.price) or bar.price <= 0:
            raise TdxResponseError(f"{context}[{index}] 价格非法: {bar.price}")
        if bar.vol < 0:
            raise TdxResponseError(f"{context}[{index}] 成交量为负: {bar.vol}")
        if reference_price and not reference_price / 100 <= bar.price <= reference_price * 100:
            raise TdxResponseError(
                f"{context}[{index}] 价格 {bar.price} 与参考价 {reference_price} 严重偏离"
            )


def _before_a_share_session(now: datetime) -> bool:
    return now.weekday() >= 5 or (now.hour, now.minute) < (9, 15)


def _historical_fund_flow_from_records(
    date: int, records: list[TransactionRecord]
) -> HistoricalFundFlow:
    flow = _classify_fund_flow(records)
    year = date // 10000
    month = (date // 100) % 100
    day = date % 100
    return HistoricalFundFlow(
        year=year,
        month=month,
        day=day,
        super_in=flow.super_in,
        super_out=flow.super_out,
        large_in=flow.large_in,
        large_out=flow.large_out,
        medium_in=flow.medium_in,
        medium_out=flow.medium_out,
        small_in=flow.small_in,
        small_out=flow.small_out,
    )


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
        timeout: float = _DEFAULT_TIMEOUT,
        auto_reconnect: bool = True,
        fallback_hosts: Sequence[str] = (),
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须至少为 1")
        self._hosts = _unique_hosts(host, fallback_hosts)
        self._host_index = 0
        self._host = self._hosts[0]
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._max_attempts = max_attempts
        self._conn = TdxConnection(self._host, port, timeout)

    # ------------------------------------------------------------------ #
    # 工厂方法：自动优选最低延迟服务器
    # ------------------------------------------------------------------ #

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        max_attempts: int = 2,
    ) -> "TdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟的建立连接。

        若所有服务器均不可达，回退到 hosts[0]。
        """
        ranked = ping_all(hosts, port, ping_timeout)
        ordered = [item[0] for item in ranked] or list(hosts)
        if not ordered:
            raise ValueError("hosts 不能为空")
        return cls(
            ordered[0],
            port,
            timeout,
            auto_reconnect,
            fallback_hosts=ordered[1:],
            max_attempts=max_attempts,
        )

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
        """执行命令；传输或响应错误时使用全新连接并按主机顺序重试。"""
        attempts = self._max_attempts if self._auto_reconnect else 1
        last_error: TdxConnectionError | TdxDecodeError | TdxResponseError | None = None
        for attempt in range(attempts):
            if attempt > 0:
                self._conn.close()
                self._host_index = (self._host_index + 1) % len(self._hosts)
                self._host = self._hosts[self._host_index]
                self._conn = TdxConnection(self._host, self._port, self._timeout)
            try:
                if not self._conn.is_connected:
                    self._conn.connect()
                return self._conn.execute(cmd)
            except (TdxConnectionError, TdxDecodeError, TdxResponseError) as error:
                last_error = error
                self._conn.close()
        assert last_error is not None
        raise last_error

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
        """批量获取实时五档行情；超过 80 只时自动按协议上限分片。"""
        if not stocks:
            raise ValueError("stocks 不能为空")
        if len(set(stocks)) != len(stocks):
            raise ValueError("stocks 不能包含重复证券")
        quotes: list[SecurityQuote] = []
        for start in range(0, len(stocks), 80):
            batch: list[SecurityQuote] = self._execute(
                GetSecurityQuotesCmd(stocks[start:start + 80])
            )
            quotes.extend(batch)
        return quotes

    def get_price_limits(
        self, market: Market, code: str, name: str, pre_close: float
    ) -> tuple[float | None, float | None]:
        """按当前交易状态计算涨跌停价。

        对上市初期不设涨跌幅限制的标的，会先用日 K 线条数估算已上市交易天数。
        """
        listed_days: int | None = None
        no_limit_window_days = get_no_limit_window_days(market, code, name)
        if no_limit_window_days > 0:
            try:
                bars = self.get_security_bars(
                    market, code, KlineCategory.DAY, 0, no_limit_window_days + 1
                )
                listed_days = len(bars)
            except Exception:
                listed_days = None

        return compute_price_limits(
            market,
            code,
            name,
            pre_close,
            listed_days=listed_days,
        )

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
        bars = self._execute(GetSecurityBarsCmd(market, code, category, start, count))
        _validate_bars(bars, "security_bars")
        return bars

    def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[IndexBar]:
        """获取指数 K 线数据。"""
        bars = self._execute(GetIndexBarsCmd(market, code, category, start, count))
        _validate_bars(bars, "index_bars")
        return bars

    def get_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar] | list[IndexBar]:
        """按市场与代码自动路由股票或指数 K 线。"""
        if _looks_like_index(market, code):
            return self.get_index_bars(market, code, category, start, count)
        return self.get_security_bars(market, code, category, start, count)

    def get_bars_range(
        self,
        market: Market,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
    ) -> list[SecurityBar] | list[IndexBar]:
        """分页获取日期闭区间内的 K 线，并按时间升序去重返回。"""
        validate_date(start_date)
        validate_date(end_date)
        if start_date > end_date:
            raise ValueError("start_date 不能晚于 end_date")
        collected: dict[tuple[int, int, int, int, int], SecurityBar] = {}
        page_start = 0
        for _ in range(256):
            page = self.get_bars(market, code, category, page_start, 800)
            if not page:
                break
            for bar in page:
                bar_date = _date_from_bar(bar)
                if start_date <= bar_date <= end_date:
                    key = (bar.year, bar.month, bar.day, bar.hour, bar.minute)
                    collected[key] = bar
            if min(_date_from_bar(bar) for bar in page) <= start_date or len(page) < 800:
                break
            page_start += len(page)
        return [collected[key] for key in sorted(collected)]

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        """获取今日分时数据（240条）。"""
        today = _today_in_shanghai()
        try:
            bars = self.get_history_minute_time_data(market, code, today)
            if bars:
                return bars
        except Exception:
            pass
        if _before_a_share_session(_now_in_shanghai()):
            return []

        bars = self._execute(GetMinuteTimeDataCmd(market, code))
        if not bars:
            return []
        reference_price: float | None = None
        try:
            quotes = self.get_security_quotes([(market, code)])
            if quotes:
                reference_price = quotes[0].pre_close or quotes[0].price
            _validate_minute_bars(bars, "minute_time", reference_price)
        except TdxResponseError:
            latest = self.get_security_bars(market, code, KlineCategory.DAY, 0, 1)
            if not latest or _date_from_bar(latest[-1]) != today:
                return []
            raise
        return bars

    def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        """获取历史某日分时数据（date: YYYYMMDD）。"""
        bars = self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))
        _validate_minute_bars(bars, "history_minute_time")
        return bars

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
        for _ in range(256):
            if pos >= size:
                break
            chunk = self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                raise TdxResponseError(f"{filename} 在偏移 {pos} 提前结束")
            full_data.extend(chunk)
            pos += len(chunk)
        if len(full_data) != size:
            raise TdxResponseError(
                f"{filename} 长度不符: expected={size}, actual={len(full_data)}"
            )
        if len(_hash) == 32 and hashlib.md5(full_data).hexdigest() != _hash.lower():
            raise TdxResponseError(f"{filename} MD5 校验失败")
        return parse_block_dat(bytes(full_data), filename)

    def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件（如 'base_info.zip'）。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        previous_chunk: bytes | None = None
        for _ in range(256):
            chunk = self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            if chunk == previous_chunk:
                raise TdxResponseError(f"{filename} 在偏移 {pos} 返回重复分片")
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
            previous_chunk = chunk
        else:
            raise TdxResponseError(f"{filename} 超过最大分片数 256")
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

    def _collect_transaction_records(
        self,
        fetch_page: Callable[[int, int], list[TransactionRecord]],
        page_size: int,
        max_start: int = 10000,
    ) -> list[TransactionRecord]:
        all_recs: list[TransactionRecord] = []
        seen_page_sigs: set[
            tuple[tuple[int, int, float, int, int, int, int | None], ...]
        ] = set()
        start = 0

        while start < max_start:
            recs = fetch_page(start, page_size)
            if not recs:
                break

            page_sig = _page_signature(recs)
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            overlap = _boundary_overlap(all_recs, recs)
            new_records = recs[overlap:]
            if not new_records:
                break
            all_recs.extend(new_records)

            start += len(recs)
            if len(recs) < page_size:
                break

        return all_recs

    def get_fund_flow(self, market: Market, code: str) -> FundFlow:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        records = self._collect_transaction_records(
            lambda start, page_size: self.get_transaction_data(market, code, start, page_size),
            2000,
        )
        return _classify_fund_flow(records)

    def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> list[HistoricalFundFlow]:
        """获取个股历史日线资金流向序列。

        优先走 Category 22 直连接口；若服务器返回空列表，则自动回退为
        “日 K 线取日期 + 历史逐笔成交重算资金流”的兼容实现。
        """
        try:
            direct = self._execute(GetHistoryFundFlowCmd(market, code, start, count))
        except Exception:
            direct = []
        if direct:
            return direct

        bars = self.get_security_bars(market, code, KlineCategory.DAY, start, count)
        results: list[HistoricalFundFlow] = []
        for bar in bars:
            date = _date_from_bar(bar)
            records = self._collect_transaction_records(
                lambda page_start, page_size: self.get_history_transaction_data(
                    market, code, date, page_start, page_size
                ),
                800,
            )
            results.append(_historical_fund_flow_from_records(date, records))
        return results


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
        timeout: float = _DEFAULT_TIMEOUT,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
        fallback_hosts: Sequence[str] = (),
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须至少为 1")
        self._hosts = _unique_hosts(host, fallback_hosts)
        self._host_index = 0
        self._host = self._hosts[0]
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._max_attempts = max_attempts
        self._conn = AsyncTdxConnection(self._host, port, timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    @classmethod
    async def from_best_host(
        cls,
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
        max_attempts: int = 2,
    ) -> "AsyncTdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟的建立连接。"""
        ranked = await ping_all_async(hosts, port, ping_timeout)
        ordered = [item[0] for item in ranked] or list(hosts)
        if not ordered:
            raise ValueError("hosts 不能为空")
        return cls(
            ordered[0],
            port,
            timeout,
            auto_reconnect,
            heartbeat_interval,
            fallback_hosts=ordered[1:],
            max_attempts=max_attempts,
        )

    @staticmethod
    async def ping_all(
        hosts: list[str] = KNOWN_HOSTS,
        port: int = _DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        return await ping_all_async(hosts, port, timeout)

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
        """执行命令；传输或响应错误时使用全新连接并按主机顺序重试。"""
        async with self._execute_lock:
            attempts = self._max_attempts if self._auto_reconnect else 1
            last_error: TdxConnectionError | TdxDecodeError | TdxResponseError | None = None
            for attempt in range(attempts):
                if attempt > 0:
                    await self._conn.close()
                    self._host_index = (self._host_index + 1) % len(self._hosts)
                    self._host = self._hosts[self._host_index]
                    self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
                try:
                    if not self._conn.is_connected:
                        await self._conn.connect()
                    return await self._conn.execute(cmd)
                except (TdxConnectionError, TdxDecodeError, TdxResponseError) as error:
                    last_error = error
                    await self._conn.close()
            assert last_error is not None
            raise last_error

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
        if not stocks:
            raise ValueError("stocks 不能为空")
        if len(set(stocks)) != len(stocks):
            raise ValueError("stocks 不能包含重复证券")
        quotes: list[SecurityQuote] = []
        for start in range(0, len(stocks), 80):
            batch: list[SecurityQuote] = await self._execute(
                GetSecurityQuotesCmd(stocks[start:start + 80])
            )
            quotes.extend(batch)
        return quotes

    async def get_price_limits(
        self, market: Market, code: str, name: str, pre_close: float
    ) -> tuple[float | None, float | None]:
        """按当前交易状态计算涨跌停价。"""
        listed_days: int | None = None
        no_limit_window_days = get_no_limit_window_days(market, code, name)
        if no_limit_window_days > 0:
            try:
                bars = await self.get_security_bars(
                    market, code, KlineCategory.DAY, 0, no_limit_window_days + 1
                )
                listed_days = len(bars)
            except Exception:
                listed_days = None

        return compute_price_limits(
            market,
            code,
            name,
            pre_close,
            listed_days=listed_days,
        )

    async def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar]:
        bars = await self._execute(
            GetSecurityBarsCmd(market, code, category, start, count)
        )
        _validate_bars(bars, "security_bars")
        return bars

    async def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[IndexBar]:
        bars = await self._execute(GetIndexBarsCmd(market, code, category, start, count))
        _validate_bars(bars, "index_bars")
        return bars

    async def get_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> list[SecurityBar] | list[IndexBar]:
        if _looks_like_index(market, code):
            return await self.get_index_bars(market, code, category, start, count)
        return await self.get_security_bars(market, code, category, start, count)

    async def get_bars_range(
        self,
        market: Market,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
    ) -> list[SecurityBar] | list[IndexBar]:
        validate_date(start_date)
        validate_date(end_date)
        if start_date > end_date:
            raise ValueError("start_date 不能晚于 end_date")
        collected: dict[tuple[int, int, int, int, int], SecurityBar] = {}
        page_start = 0
        for _ in range(256):
            page = await self.get_bars(market, code, category, page_start, 800)
            if not page:
                break
            for bar in page:
                bar_date = _date_from_bar(bar)
                if start_date <= bar_date <= end_date:
                    key = (bar.year, bar.month, bar.day, bar.hour, bar.minute)
                    collected[key] = bar
            if min(_date_from_bar(bar) for bar in page) <= start_date or len(page) < 800:
                break
            page_start += len(page)
        return [collected[key] for key in sorted(collected)]

    async def get_minute_time_data(self, market: Market, code: str) -> list[MinuteBar]:
        today = _today_in_shanghai()
        try:
            bars = await self.get_history_minute_time_data(market, code, today)
            if bars:
                return bars
        except Exception:
            pass
        if _before_a_share_session(_now_in_shanghai()):
            return []

        bars = await self._execute(GetMinuteTimeDataCmd(market, code))
        if not bars:
            return []
        reference_price: float | None = None
        try:
            quotes = await self.get_security_quotes([(market, code)])
            if quotes:
                reference_price = quotes[0].pre_close or quotes[0].price
            _validate_minute_bars(bars, "minute_time", reference_price)
        except TdxResponseError:
            latest = await self.get_security_bars(market, code, KlineCategory.DAY, 0, 1)
            if not latest or _date_from_bar(latest[-1]) != today:
                return []
            raise
        return bars

    async def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> list[MinuteBar]:
        bars = await self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))
        _validate_minute_bars(bars, "history_minute_time")
        return bars

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
        for _ in range(256):
            if pos >= size:
                break
            chunk = await self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                raise TdxResponseError(f"{filename} 在偏移 {pos} 提前结束")
            full_data.extend(chunk)
            pos += len(chunk)
        if len(full_data) != size:
            raise TdxResponseError(
                f"{filename} 长度不符: expected={size}, actual={len(full_data)}"
            )
        if len(_hash) == 32 and hashlib.md5(full_data).hexdigest() != _hash.lower():
            raise TdxResponseError(f"{filename} MD5 校验失败")
        return parse_block_dat(bytes(full_data), filename)

    async def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        previous_chunk: bytes | None = None
        for _ in range(256):
            chunk = await self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            if chunk == previous_chunk:
                raise TdxResponseError(f"{filename} 在偏移 {pos} 返回重复分片")
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
            previous_chunk = chunk
        else:
            raise TdxResponseError(f"{filename} 超过最大分片数 256")
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

    async def _collect_transaction_records(
        self,
        fetch_page: Callable[[int, int], Awaitable[list[TransactionRecord]]],
        page_size: int,
        max_start: int = 10000,
    ) -> list[TransactionRecord]:
        all_recs: list[TransactionRecord] = []
        seen_page_sigs: set[
            tuple[tuple[int, int, float, int, int, int, int | None], ...]
        ] = set()
        start = 0

        while start < max_start:
            recs = await fetch_page(start, page_size)
            if not recs:
                break

            page_sig = _page_signature(recs)
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            overlap = _boundary_overlap(all_recs, recs)
            new_records = recs[overlap:]
            if not new_records:
                break
            all_recs.extend(new_records)

            start += len(recs)
            if len(recs) < page_size:
                break

        return all_recs

    async def get_fund_flow(self, market: Market, code: str) -> FundFlow:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        records = await self._collect_transaction_records(
            lambda start, page_size: self.get_transaction_data(
                market, code, start, page_size
            ),
            2000,
        )
        return _classify_fund_flow(records)

    async def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> list[HistoricalFundFlow]:
        """获取个股历史日线资金流向序列。

        优先走 Category 22 直连接口；若服务器返回空列表，则自动回退为
        “日 K 线取日期 + 历史逐笔成交重算资金流”的兼容实现。
        """
        try:
            direct = await self._execute(GetHistoryFundFlowCmd(market, code, start, count))
        except Exception:
            direct = []
        if direct:
            return direct

        bars = await self.get_security_bars(market, code, KlineCategory.DAY, start, count)
        results: list[HistoricalFundFlow] = []
        for bar in bars:
            date = _date_from_bar(bar)
            records = await self._collect_transaction_records(
                lambda page_start, page_size: self.get_history_transaction_data(
                    market, code, date, page_start, page_size
                ),
                800,
            )
            results.append(_historical_fund_flow_from_records(date, records))
        return results
