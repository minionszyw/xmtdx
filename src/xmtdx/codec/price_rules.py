"""A 股价格限制规则引擎。"""

from ..models.enums import Market
from ..models.finance import FinanceInfo


def compute_price_limits(
    market: Market,
    code: str,
    name: str,
    pre_close: float,
    finance_info: FinanceInfo | None = None,
) -> tuple[float | None, float | None]:
    """根据板块规则计算涨跌停价。

    Returns:
        (limit_up, limit_down)

    无涨跌幅限制或当前规则无法可靠判断时返回 ``(None, None)``。
    """
    if pre_close <= 0:
        return None, None

    upper_name = name.upper()

    # 指数/板块类代码通常无涨跌停。
    # 这里优先用明确的指数代码段判断，再用名称兜底，避免把真实股票误判成指数。
    is_index = False
    if market == Market.SH and code.startswith(
        ("000", "880", "881", "882", "883", "884", "885", "999")
    ):
        is_index = True
    elif market == Market.SZ and code.startswith(("395", "399")):
        is_index = True
    elif "指数" in name or "板块" in name:
        is_index = True

    if is_index:
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

    # TODO: 上市前 5 日无涨跌幅限制判断（需要 ipo_date 或更明确的上市状态标识）。
    _ = finance_info

    def _round_price(p: float) -> float:
        return round(p + 0.00001, 2)

    limit_up = _round_price(pre_close * (1 + limit_pct))
    limit_down = _round_price(pre_close * (1 - limit_pct))

    return limit_up, limit_down
