"""未知字段探测脚本：通过批量拉取多只股票数据，尝试推断各 unknown_N 字段的含义。

用法：
    cd /home/m/xmtdx
    python3 scripts/probe_unknowns.py

输出：
    1. MinuteBar.unknown_1 vs 分钟均价（累计成交额 / 累计成交量）
    2. SecurityQuote.unknown_2/3/5/6/7/8 与已知行情指标的相关关系
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from xmtdx import TdxClient, Market, KlineCategory

HOST = "180.153.18.170"

# 沪深各取若干活跃股票
SH_CODES = ["600000", "600036", "601318", "600519", "601628"]
SZ_CODES = ["000001", "000002", "000858", "002415", "300750"]

SEP = "-" * 72


# ---------------------------------------------------------------------------
# Part 1: MinuteBar.unknown_1 — 是否为分钟均价？
# ---------------------------------------------------------------------------

def probe_minute_unknown_1(c: TdxClient) -> None:
    print(SEP)
    print("Part 1: MinuteBar.unknown_1 vs 分钟均价 (历史某日)")
    print(SEP)

    # 使用历史分时，数据确定（不随时间变化）
    DATE = 20250108
    code, market = "600000", Market.SH

    bars = c.get_history_minute_time_data(market, code, DATE)
    print(f"  {market.name} {code}  日期={DATE}  共 {len(bars)} 条分时\n")

    # 同时拉取当日日线 K 作为参考（含 amount/vol 可算均价）
    # 分时数据无直接成交额，需要用 price × vol 近似
    # 若 unknown_1 == round(price × 100) 则为原始价格单位均价
    print(f"  {'分钟':>6}  {'price':>8}  {'vol':>8}  {'unknown_1':>12}  {'price*100':>10}  {'diff':>8}")
    print(f"  {'':-<6}  {'':-<8}  {'':-<8}  {'':-<12}  {'':-<10}  {'':-<8}")

    exact_match = 0
    close_match = 0

    for i, b in enumerate(bars[:30]):  # 只打印前30条
        price_x100 = round(b.price * 100)
        diff = b.unknown_1 - price_x100
        exact = b.unknown_1 == price_x100
        close = abs(diff) <= 2

        if exact:
            exact_match += 1
        if close:
            close_match += 1

        flag = " <<< exact" if exact else (" ≈" if close else "")
        print(f"  {i+1:>6}  {b.price:>8.2f}  {b.vol:>8}  {b.unknown_1:>12}  {price_x100:>10}  {diff:>+8}{flag}")

    # Count across all bars
    all_exact = sum(1 for b in bars if b.unknown_1 == round(b.price * 100))
    all_close = sum(1 for b in bars if abs(b.unknown_1 - round(b.price * 100)) <= 2)

    print(f"\n  全部 {len(bars)} 条：")
    print(f"    unknown_1 == price*100 (精确): {all_exact}/{len(bars)} ({100*all_exact/len(bars):.1f}%)")
    print(f"    unknown_1 ≈ price*100 (±2):    {all_close}/{len(bars)} ({100*all_close/len(bars):.1f}%)")

    # Try another hypothesis: unknown_1 is a cumulative average price (均价)
    # Compute running avg: sum(price*vol)/sum(vol)
    print(f"\n  另一假设：unknown_1 = 当日累计均价×100")
    cum_pv = 0.0
    cum_v = 0
    correct_avg = 0
    for b in bars:
        cum_pv += b.price * b.vol
        cum_v += b.vol
        if cum_v > 0:
            avg = cum_pv / cum_v
            expected = round(avg * 100)
            if abs(b.unknown_1 - expected) <= 2:
                correct_avg += 1

    print(f"    unknown_1 ≈ 累计均价×100 (±2): {correct_avg}/{len(bars)} ({100*correct_avg/len(bars):.1f}%)")


# ---------------------------------------------------------------------------
# Part 2: SecurityQuote.unknown_N fields
# ---------------------------------------------------------------------------

def probe_quote_unknowns(c: TdxClient) -> None:
    print(f"\n{SEP}")
    print("Part 2: SecurityQuote.unknown_2/3/5/6/7/8 — 与已知字段的关系")
    print(SEP)

    pairs = [(Market.SH, code) for code in SH_CODES] + [(Market.SZ, code) for code in SZ_CODES]
    quotes = c.get_security_quotes(pairs)

    print(f"  {'market':>6}  {'code':>8}  {'pre_close':>10}  {'price':>8}  "
          f"{'u2':>6}  {'u3':>8}  {'u5':>6}  {'u6':>6}  {'u7':>6}  {'u8':>6}  {'rise_spd':>10}")
    print(f"  {'':-<6}  {'':-<8}  {'':-<10}  {'':-<8}  "
          f"{'':-<6}  {'':-<8}  {'':-<6}  {'':-<6}  {'':-<6}  {'':-<6}  {'':-<10}")

    for q in quotes:
        pct = (q.price - q.pre_close) / q.pre_close * 100 if q.pre_close else 0
        print(
            f"  {q.market.name:>6}  {q.code:>8}  {q.pre_close:>10.2f}  {q.price:>8.2f}  "
            f"{q.unknown_2:>6}  {q.unknown_3:>8}  {q.unknown_5:>6}  "
            f"{q.unknown_6:>6}  {q.unknown_7:>6}  {q.unknown_8:>6}  {q.rise_speed:>10.4f}"
        )

    print(f"\n  注：rise_speed = reversed_bytes9/100（已确认 = 涨速）")

    # Hypothesis: unknown_3 might relate to 涨停/跌停 price
    # 涨停 = pre_close * 1.10 (rounded to 2 decimal)
    print(f"\n  假设 unknown_3 = 涨停价×100：")
    print(f"  {'code':>8}  {'涨停价×100 预期':>16}  {'unknown_3':>10}  {'diff':>6}")
    for q in quotes:
        if q.pre_close > 0:
            limit_up = round(q.pre_close * 1.10 * 100)
            diff = q.unknown_3 - limit_up
            print(f"  {q.code:>8}  {limit_up:>16}  {q.unknown_3:>10}  {diff:>+6}")

    print(f"\n  假设 unknown_3 = 跌停价×100：")
    print(f"  {'code':>8}  {'跌停价×100 预期':>16}  {'unknown_3':>10}  {'diff':>6}")
    for q in quotes:
        if q.pre_close > 0:
            limit_dn = round(q.pre_close * 0.90 * 100)
            diff = q.unknown_3 - limit_dn
            print(f"  {q.code:>8}  {limit_dn:>16}  {q.unknown_3:>10}  {diff:>+6}")

    # unknown_2: often -1 or small value — check if it's 换手率×10000 or similar
    print(f"\n  unknown_2 raw values: {[q.unknown_2 for q in quotes]}")
    print(f"  unknown_5 raw values: {[q.unknown_5 for q in quotes]}")
    print(f"  unknown_6 raw values: {[q.unknown_6 for q in quotes]}")
    print(f"  unknown_7 raw values: {[q.unknown_7 for q in quotes]}")
    print(f"  unknown_8 raw values: {[q.unknown_8 for q in quotes]}")

    # Print raw bytes for manual inspection
    print(f"\n  原始字节（前20字节 hex）：")
    for q in quotes:
        print(f"    {q.code}: {q._raw[:20].hex()}")


# ---------------------------------------------------------------------------
# Part 3: TransactionRecord.unknown_last — 是否为秒数？
# ---------------------------------------------------------------------------

def probe_transaction_unknown_last(c: TdxClient) -> None:
    print(f"\n{SEP}")
    print("Part 3: TransactionRecord.unknown_last — 是否为秒或序号？")
    print(SEP)

    recs = c.get_history_transaction_data(Market.SH, "600000", 20250108, 0, 30)
    print(f"  {'序号':>4}  {'时间':>6}  {'price':>8}  {'vol':>6}  {'buy':>4}  {'unknown_last':>14}")
    print(f"  {'':-<4}  {'':-<6}  {'':-<8}  {'':-<6}  {'':-<4}  {'':-<14}")

    for i, r in enumerate(recs):
        print(f"  {i+1:>4}  {r.hour:02d}:{r.minute:02d}  {r.price:>8.2f}  {r.vol:>6}  {r.buyorsell:>4}  {r.unknown_last:>14}")

    unique = len({r.unknown_last for r in recs})
    print(f"\n  unknown_last 唯一值数量: {unique}/{len(recs)}")
    print(f"  值分布: {sorted({r.unknown_last for r in recs})}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"连接 {HOST}:7709 ...")
    with TdxClient(HOST) as c:
        probe_minute_unknown_1(c)
        probe_quote_unknowns(c)
        probe_transaction_unknown_last(c)

    print(f"\n{SEP}")
    print("探测完成。根据以上输出可判断各字段含义，更新 models/ 文档注释。")


if __name__ == "__main__":
    main()
