"""验证涨跌停价。"""
import sys
import pathlib

# 添加 src 到 path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from xmtdx import TdxClient, Market

def main():
    print("正在连接服务器验证涨跌停...")
    with TdxClient.from_best_host() as c:
        # 选取一些知名 A 股
        stocks = [(Market.SH, "600000"), (Market.SZ, "000001"), (Market.SZ, "300750")]
        quotes = c.get_security_quotes(stocks)
        
        print(f"  {'代码':>8}  {'昨收':>8}  {'现价':>8}  {'涨停价':>8}  {'跌停价':>8}  {'涨速':>8}")
        for q in quotes:
            print(f"  {q.code:>8}  {q.pre_close:>8.2f}  {q.price:>8.2f}  {q.limit_up:>8.2f}  {q.limit_down:>8.2f}  {q.rise_speed:>8.2f}")
            
            # 校验涨停价是否大约为昨收 * 1.1 (主板/深证) 或 * 1.2 (创业板)
            expected_up = round(q.pre_close * (1.2 if q.code.startswith("300") else 1.1), 2)
            if abs(q.limit_up - expected_up) > 0.02:
                print(f"    [!] 涨停价异常：预期约 {expected_up}")

if __name__ == "__main__":
    main()
