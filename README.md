# xmtdx

通达信 TCP 协议 A 股行情数据客户端，零运行时依赖。

pytdx 年久失修：多处已知解析 bug、Python 2 包袱、无类型注解、大量未知字段被静默丢弃。xmtdx 重新实现协议，修复已知 bug，保留全部原始字节与未知字段供后续逆向分析。

## 特性

- **零依赖**：纯标准库，Python ≥ 3.10
- **同步 + asyncio 双接口**：`TdxClient` / `AsyncTdxClient`，commands 层不含任何 IO
- **完整类型注解**：strict `mypy` + `ruff` 通过
- **高可用传输**：同步/异步均支持 `ping_all()`、`from_best_host()`、断线自动重连
- **修复 pytdx 已知 bug**（见下文）
- **保留原始字节**：每条数据记录含 `_raw: bytes`，未知字段以 `unknown_N` 命名而非丢弃
- **保活心跳机制**：`AsyncTdxClient` 自动发送心跳包，确保长连接生产环境稳定性
- **全市场覆盖**：完整支持沪深京三市 A 股（SH/SZ/BJ），自动过滤非 A 股品种
- **全市场涨跌统计**：一键获取全 A 股涨/跌/平家数及总成交额
- **离线 + 本地传输回归测试**：覆盖解析、异步并发串行化、超时、自动重连与坏包处理

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                  # 开发模式
pip install -e ".[dev]"           # 含测试/类型检查工具
pip install -e ".[pandas]"        # 含 pandas（可选）
```

## 快速开始

### 同步

```python
from xmtdx import TdxClient, Market, KlineCategory

# 指定服务器
with TdxClient("180.153.18.170") as c:
    count = c.get_security_count(Market.SH)
    bars  = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)
    for b in bars:
        print(b.year, b.month, b.day, b.open, b.close, b.high, b.low, b.vol)

# 自动测速选最低延迟服务器
with TdxClient.from_best_host() as c:
    quotes = c.get_security_quotes([(Market.SH, "600000"), (Market.SZ, "000001")])
    print(quotes[0].price, quotes[0].bid1, quotes[0].ask1)
```

### asyncio

```python
import asyncio
from xmtdx import AsyncTdxClient, Market, KlineCategory

async def main():
    async with AsyncTdxClient("180.153.18.170") as c:
        bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)
        print(bars[0])

asyncio.run(main())
```

### 高可用工具

```python
from xmtdx import ping_all, KNOWN_HOSTS

# 并发测速，返回按延迟排序的 [(host, seconds), ...]
results = ping_all(KNOWN_HOSTS, timeout=5.0)
for host, ms in results:
    print(f"{host}  {ms*1000:.0f} ms")

# 自动选最优服务器
with TdxClient.from_best_host(ping_timeout=5.0) as c:
    ...

# asyncio 版本同样支持
client = AsyncTdxClient.from_best_host(ping_timeout=5.0)
```

内置服务器列表（`KNOWN_HOSTS`）：

```
180.153.18.170  180.153.18.171  180.153.18.172
115.238.56.198  115.238.90.165  218.75.126.9
47.107.75.159   59.175.238.38
```


## API

### TdxClient

| 方法 | 说明 |
|------|------|
| `get_security_count(market)` | 市场证券总数 |
| `get_security_list(market, start)` | 证券列表（每页 ~1000 条） |
| `get_security_list_all()` | 沪深 A 股列表（自动挂载行业信息；BJ 暂未纳入） |
| `get_market_stat()` | 全市场 A 股涨跌统计（家数、成交额） |
| `get_security_quotes([(market, code), ...])` | 批量实时五档行情（最多 80 只/次） |
| `get_price_limits(market, code, name, pre_close)` | 计算当前涨跌停价（自动处理上市初期无涨跌幅限制） |
| `get_security_bars(market, code, category, start, count=800)` | K 线（股票） |
| `get_index_bars(market, code, category, start, count=800)` | K 线（指数） |
| `get_minute_time_data(market, code)` | 今日分时（240 条） |
| `get_history_minute_time_data(market, code, date)` | 历史某日分时，`date=YYYYMMDD` |
| `get_transaction_data(market, code, start, count=800)` | 当日逐笔成交（分页） |
| `get_history_transaction_data(market, code, date, start, count=800)` | 历史逐笔成交 |
| `get_fund_flow(market, code)` | 当日资金流向统计（超大/大/中/小单） |
| `get_history_fund_flow(market, code, start, count)` | 历史日线资金流向序列（优先 Category 22，空回包时自动回退到历史逐笔重算） |
| `get_xdxr_info(market, code)` | 除权除息历史 |
| `get_finance_info(market, code)` | 最新财务数据 |
| `get_company_info_category(market, code)` | 公司信息文件目录 |
| `get_company_info_content(market, code, filename, offset, length)` | 公司信息文本 |
| `get_block_info(filename)` | 板块信息（行业、概念、风格等） |
| `get_report_file(filename)` | 批量拉取大文件（如 'base_info.zip', 'gpcw.txt'） |

`AsyncTdxClient` 提供与同步版对应的查询方法与高可用入口，均为 `async def`。
单个 `AsyncTdxClient` 仅维护一条 TCP 连接；并发调用会在连接内串行执行。

### KlineCategory

```
MIN_1  MIN_3  MIN_5  MIN_15  MIN_30  MIN_60
DAY  WEEK  MONTH  SEASON  YEAR  YEAR_ALT
```

## 数据模型

所有 dataclass 字段均有类型注解。每条记录附带 `_raw: bytes`（原始协议字节）。

### SecurityBar（K 线）

```
open  close  high  low  vol  amount
year  month  day  hour  minute
_raw
```

### SecurityQuote（实时行情）

```
market  code  price  pre_close  open  high  low
vol  cur_vol  amount  s_vol  b_vol
bid1..bid5  bid_vol1..bid_vol5
ask1..ask5  ask_vol1..ask_vol5
rise_speed  limit_up  limit_down  server_time
unknown_2..unknown_3  unknown_5..unknown_8
_raw
```

`limit_up` / `limit_down` 当前不再直接由协议字段映射，默认保留为 `None`；
建议通过 `client.get_price_limits(...)` 计算当前涨跌停价，或用
`xmtdx.codec.price_rules.compute_price_limits(..., listed_days=...)` 做纯规则计算。

### MinuteBar（分时）

```
price  vol
unknown_1   # 原 pytdx 丢弃字段，保留供分析（≠ 均价）
_raw
```

### TransactionRecord（逐笔成交）

```
hour  minute  price  vol
buyorsell   # 0=买, 1=卖, 2=中性, 8=集合竞价
unknown_last
_raw
```

### SecurityInfo（证券列表）

```
market  code  name  volunit  decimal_point  pre_close
industry_tdx  industry_sw
```

### XdxrRecord（除权除息）

```
market  code  year  month  day  category  name
fenhong  peigujia  songzhuangu  peigu  suogu
xingquanjia  fenshu
panqian_liutong  panhou_liutong      # 单位：万股
qian_zongguben  hou_zongguben        # 单位：万股
_raw
```

### FinanceInfo（财务）

流通股本、总股本、各省份/行业代码、资产负债表及利润表主要科目（30 个 float 字段）。

### CompanyInfoCategory（公司信息目录）

```
name  filename  start  length
```

### TdxBlock（板块信息）

```
name  category  count  codes
```

### FundFlow（资金流）

```
super_in/out  large_in/out  medium_in/out  small_in/out
main_net_inflow  total_net_inflow
```

### HistoricalFundFlow（历史资金流序列）

```
year  month  day
super_in/out  large_in/out  medium_in/out  small_in/out
main_net_inflow
```

## 修复的 pytdx Bug


| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 1 | `xdxr_info` | 循环内始终读 `body[:7]`，所有记录字段相同 | 改为从当前 `pos` 读取，pos 正确推进 |
| 2 | `security_list` | GBK 解码截断时 crash | `decode('gbk', errors='replace')` |
| 3 | `security_list` | `pre_close` 误当作整数价格 `/100` | 恢复为通达信自定义浮点解码 |
| 4 | `transaction` | 最后一个字段被 `_` 丢弃 | 保留为 `unknown_last` |
| 5 | `minute_time` | `reversed1` 字段被丢弃 | 保留为 `unknown_1` |
| 6 | `xdxr_info` | 股本字段用 `float(uint32)` 直解，差约 374 倍 | 改用 `_decode_volume`（通达信自定义浮点），单位万股，与 `FinanceInfo` 完全吻合 |
| 7 | `security_quotes` | 涨停/跌停价映射错误或缺失 | 停止使用不可信协议位，改由业务规则计算 |

## 架构

```
src/xmtdx/
├── client.py          # TdxClient / AsyncTdxClient（高层 API）
├── transport/
│   ├── sync.py        # TdxConnection（socket）+ ping_host / ping_all
│   └── async_.py      # AsyncTdxConnection（asyncio）
├── commands/          # 每条命令：build_request() + parse_response()，无 IO
├── codec/             # price / volume / datetime / frame 编解码
└── models/            # 纯 dataclass，无业务逻辑
```

commands 层不依赖 transport，可独立单测。transport 层负责 TCP、握手、帧解压、分发。

## 开发

```bash
# 单元测试（无需网络）
python -m pytest tests/unit/

# 集成测试（需要网络，默认跳过）
XMTDX_LIVE=1 python -m pytest tests/integration/

# 未知字段探测脚本
python scripts/probe_unknowns.py

# 类型检查
mypy src/

# lint
ruff check src/ tests/
```

## 协议说明

通达信使用私有二进制 TCP 协议：

- **帧格式**：16 字节响应头（含 zipsize / unzipsize），body 按需 zlib 解压
- **价格编码**：变长有符号整数（类 LEB128，bit8=继续，bit7=符号，首字节低 6 位 + 后续低 7 位）
- **成交量编码**：4 字节自定义浮点（字节 3 = 指数，字节 0-2 = 精度），**不可用于价格字段**
- **握手**：连接后必须顺序发送 3 条 setup 命令，响应丢弃
- **价格存储**：整数 × 100，差分编码（相邻 tick 存 delta）
