"""A 股价格限制规则引擎。"""

from ..models.enums import Market
from ..models.finance import FinanceInfo


def get_no_limit_window_days(market: Market, code: str, name: str) -> int:
    """返回上市初期不设涨跌幅限制的交易日窗口。

    返回值:
        0: 默认按常规涨跌幅限制处理
        1: 北交所上市首日不设涨跌幅限制
        5: 沪深主板/创业板/科创板上市前 5 个交易日不设涨跌幅限制
    """
    if _is_index_like(market, code, name):
        return 0

    if code.startswith(("43", "83", "87", "92")):
        return 1

    if market == Market.SH and code.startswith(("60", "68")):
        return 5
    if market == Market.SZ and code.startswith(("00", "30")):
        return 5

    return 0


def _is_index_like(market: Market, code: str, name: str) -> bool:
    """判断是否为指数/板块类代码。"""
    if market == Market.SH and code.startswith(
        ("000", "880", "881", "882", "883", "884", "885", "999")
    ):
        return True
    if market == Market.SZ and code.startswith(("395", "399")):
        return True
    return "指数" in name or "板块" in name


def compute_price_limits(
    market: Market,
    code: str,
    name: str,
    pre_close: float,
    finance_info: FinanceInfo | None = None,
    listed_days: int | None = None,
) -> tuple[float | None, float | None]:
    """根据板块规则计算涨跌停价。

    Returns:
        (limit_up, limit_down)

    无涨跌幅限制或当前规则无法可靠判断时返回 ``(None, None)``。

    Args:
        listed_days:
            已上市交易天数（按交易日计，首日=1）。
            若提供该值，函数会按上市初期无涨跌幅限制规则优先返回 ``(None, None)``。
    """
    if pre_close <= 0:
        return None, None

    upper_name = name.upper()

    # 指数/板块类代码通常无涨跌停。
    if _is_index_like(market, code, name):
        return None, None

    no_limit_window_days = get_no_limit_window_days(market, code, name)
    if listed_days is not None and 0 < listed_days <= no_limit_window_days:
        return None, None

    limit_pct = 0.10  # 默认 10%

    # 2. ST / *ST 判断
    if "ST" in upper_name:
        limit_pct = 0.05
    # 3. 科创板 (688) / 创业板 (300, 301)
    elif code.startswith("688") or code.startswith("300") or code.startswith("301"):
        limit_pct = 0.20
    # 4. 北交所 (43, 83, 87, 92)
    elif code.startswith(("43", "83", "87", "92")):
        limit_pct = 0.30

    # `listed_days` 是更可靠的交易日维度输入；finance_info 仍保留给上层调用方扩展。
    _ = finance_info

    def _round_price(p: float) -> float:
        return round(p + 0.00001, 2)

    limit_up = _round_price(pre_close * (1 + limit_pct))
    limit_down = _round_price(pre_close * (1 - limit_pct))

    return limit_up, limit_down
