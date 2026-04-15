"""探测未知字段含义的辅助脚本。"""

import sys

from xmtdx import Market, TdxClient


def probe_minute_averages(client, market, code):
    """探测分时数据中 unknown_1 的含义（疑似均价）。"""
    print(f"\nProbing {code} Minute Time unknown_1:")
    bars = client.get_minute_time_data(market, code)
    if not bars:
        return

    # 分时数据无直接成交额，需要用 price × vol 近似
    # 若 unknown_1 == round(price × 100) 则为原始价格单位均价
    print(f"  {'分钟':>6}  {'price':>8}  {'vol':>8}  "
          f"{'unknown_1':>12}  {'price*100':>10}  {'diff':>8}")
    print(f"  {'':-<6}  {'':-<8}  {'':-<8}  "
          f"{'':-<12}  {'':-<10}  {'':-<8}")

    all_exact = 0
    all_close = 0
    for i, b in enumerate(bars):
        price_x100 = int(round(b.price * 100))
        diff = b.unknown_1 - price_x100
        exact = (diff == 0)
        close = (abs(diff) <= 2)
        if exact:
            all_exact += 1
        if close:
            all_close += 1

        flag = " <<< exact" if exact else (" ≈" if close else "")
        print(f"  {i+1:>6}  {b.price:>8.2f}  {b.vol:>8}  "
              f"{b.unknown_1:>12}  {price_x100:>10}  {diff:>+8}{flag}")

    # Count across all bars
    print(f"\n  全部 {len(bars)} 条：")
    print(f"    unknown_1 == price*100 (精确): "
          f"{all_exact}/{len(bars)} ({100*all_exact/len(bars):.1f}%)")
    print(f"    unknown_1 ≈ price*100 (±2):    "
          f"{all_close}/{len(bars)} ({100*all_close/len(bars):.1f}%)")

    # Try another hypothesis: unknown_1 is a cumulative average price (均价)
    total_vol = 0
    total_amount = 0.0
    correct_avg = 0
    for b in bars:
        total_vol += b.vol
        total_amount += b.price * b.vol
        if total_vol > 0:
            avg_x100 = int(round((total_amount / total_vol) * 100))
            if abs(b.unknown_1 - avg_x100) <= 2:
                correct_avg += 1

    print(f"    unknown_1 ≈ 累计均价×100 (±2): "
          f"{correct_avg}/{len(bars)} ({100*correct_avg/len(bars):.1f}%)")


def probe_quote_limits(client, market, code):
    """探测实时行情中 unknown_5/6 的含义（疑似涨跌停）。"""
    print(f"\nProbing {code} Quote unknown_5/6:")
    quotes = client.get_security_quotes([(market, code)])
    if not quotes:
        return
    for q in quotes:
        print(
            f"  {q.market.name:>6}  {q.code:>8}  {q.pre_close:>10.2f}  {q.price:>8.2f}  "
            f"u5:{q.unknown_5:>6}  u6:{q.unknown_6:>6}"
        )


def probe_fund_flow_raw(client, market, code):
    """探测资金流原始数据分布。"""
    print(f"\nProbing {code} Transaction raw unknown_last:")
    # 直接用 get_transaction_data 获取原始记录
    recs = client.get_transaction_data(market, code, 0, 50)
    print(f"  {'idx':>4}  {'time':>5}  {'price':>8}  {'vol':>6}  {'b/s':>4}  {'unknown_last':>14}")
    for i, r in enumerate(recs):
        print(f"  {i+1:>4}  {r.hour:02d}:{r.minute:02d}  {r.price:>8.2f}  "
              f"{r.vol:>6}  {r.buyorsell:>4}  {r.unknown_last:>14}")

    unique = len({r.unknown_last for r in recs})
    print(f"\n  Unique unknown_last in 50 recs: {unique}")


def main():
    host = "180.153.18.170"
    if len(sys.argv) > 1:
        host = sys.argv[1]

    with TdxClient(host) as client:
        # 1. 均价探测
        probe_minute_averages(client, Market.SH, "600000")
        probe_minute_averages(client, Market.SZ, "000001")

        # 2. 涨跌停探测
        probe_quote_limits(client, Market.SH, "600000")
        probe_quote_limits(client, Market.SZ, "000001")

        # 3. 资金流探测
        probe_fund_flow_raw(client, Market.SH, "600000")


if __name__ == "__main__":
    main()
