"""实测验证脚本 (2026-04-15 修复验证)。"""

import sys

from xmtdx import Market, TdxClient
from xmtdx.models.enums import KlineCategory


def main():
    hosts = ["115.238.56.198", "180.153.18.170", "124.71.187.122"]
    host = hosts[0]
    if len(sys.argv) > 1:
        host = sys.argv[1]

    print(f"Connecting to {host}...")
    success = True

    with TdxClient(host) as client:
        # 1. 验证 K 线请求已恢复
        print("\n[1] Security/Index Bars:")
        try:
            bars = client.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 3)
            ibars = client.get_index_bars(Market.SH, "999999", KlineCategory.DAY, 0, 3)
            print(f"  600000 bars: {len(bars)}")
            print(f"  999999 index bars: {len(ibars)}")
            if not bars or not ibars:
                print("  Result: FAIL (Bars request returned empty)")
                success = False
            else:
                print("  Result: SUCCESS")
        except Exception as e:
            print(f"  Error: {e}")
            success = False

        # 2. 验证 get_market_stat (880005)
        print("\n[2] Market Stat (880005):")
        try:
            stat = client.get_market_stat()
            print(
                f"  Up: {stat.up_count}, Down: {stat.down_count}, "
                f"Neutral: {stat.neutral_count}, Suspended: {stat.suspended_count}, "
                f"Total: {stat.total_count}"
            )
            stat_sum = (
                stat.up_count
                + stat.down_count
                + stat.neutral_count
                + stat.suspended_count
            )
            print(f"  Sum (U+D+N+S): {stat_sum}")
            if stat_sum == stat.total_count:
                print("  Result: SUCCESS (residual-balanced total)")
            else:
                print("  Result: FAIL (Sum != Total)")
                success = False
        except Exception as e:
            print(f"  Error: {e}")
            success = False

        # 3. 验证价格限制计算
        print("\n[3] Price Limits:")
        samples = [
            ("600000", Market.SH, "浦发银行"),
            ("300750", Market.SZ, "宁德时代"),
            ("688981", Market.SH, "中芯国际"),
            ("999999", Market.SH, "上证指数"),
        ]
        try:
            quotes = client.get_security_quotes([(market, code) for code, market, _name in samples])
            for q, (_code, _market, name) in zip(quotes, samples, strict=True):
                lu, ld = client.get_price_limits(q.market, q.code, name, q.pre_close)
                print(
                    f"  {q.code}: Price={q.price:.2f}, PreClose={q.pre_close:.2f}, "
                    f"LimitUp={lu}, LimitDown={ld}"
                )
                if q.code == "999999":
                    if lu is not None or ld is not None:
                        print("  Result: FAIL (Index should not have price limits)")
                        success = False
                elif lu is None or ld is None:
                    print(f"  Result: FAIL (Limit calculation returned None for {q.code})")
                    success = False
        except Exception as e:
            print(f"  Error: {e}")
            success = False

        # 4. 验证 get_history_fund_flow（直连或 fallback）
        print("\n[4] History Fund Flow:")
        try:
            h_flow = client.get_history_fund_flow(Market.SH, "600000", 0, 1)
            if h_flow:
                f = h_flow[0]
                print(f"  Date: {f.year}-{f.month}-{f.day}, SuperIn: {f.super_in:.2f}")
                print("  Result: SUCCESS")
            else:
                print("  Result: FAIL (No data returned)")
                success = False
        except Exception as e:
            print(f"  Error: {e}")
            success = False

        # 5. 验证 get_fund_flow 分页
        print("\n[5] Fund Flow Pagination (600000):")
        try:
            flow = client.get_fund_flow(Market.SH, "600000")
            total_in = flow.super_in + flow.large_in + flow.medium_in + flow.small_in
            total_out = flow.super_out + flow.large_out + flow.medium_out + flow.small_out
            print(f"  600000 Classified Total: {total_in + total_out:.2f}")
            # 获取实时成交额对比
            q = client.get_security_quotes([(Market.SH, "600000")])[0]
            print(f"  600000 Real Amount: {q.amount:.2f}")
            coverage = (total_in + total_out) / q.amount if q.amount > 0 else 0
            print(f"  Coverage: {coverage * 100:.1f}%")
            if coverage < 0.90:
                print("  Result: FAIL (Coverage too low)")
                success = False
            else:
                print("  Result: SUCCESS")
        except Exception as e:
            print(f"  Error: {e}")
            success = False

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
