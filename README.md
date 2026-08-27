# xmtdx

通达信私有 7709/TCP 行情协议的 A 股客户端实现，零运行时依赖。协议并无官方公开规范，字段与命令来自兼容实现、抓包和真实服务器交叉验证，因此属于兼容性逆向开发，不包含通达信客户端代码。

当前源码版本：**0.2.1**。

pytdx 年久失修：多处已知解析 bug、Python 2 包袱、无类型注解、大量未知字段被静默丢弃。xmtdx 重新实现协议，修复已知 bug，保留全部原始字节与未知字段供后续逆向分析。

## 特性

- **零依赖**：纯标准库，Python ≥ 3.10
- **同步 + asyncio 双接口**：`TdxClient` / `AsyncTdxClient`，commands 层不含任何 IO
- **完整类型注解**：strict `mypy` + `ruff` 通过
- **高可用传输**：同步/异步均支持 `ping_all()`、`from_best_host()` 和候选服务器重试
- **响应语义校验**：校验证券身份、日期、OHLC、成交量、资金流覆盖率和文件完整性
- **批量与区间 API**：行情超过 80 只自动分片，K 线支持股票/指数自动路由和日期区间分页
- **修复 pytdx 已知 bug**（见下文）
- **保留原始字节**：每条数据记录含 `_raw: bytes`，未知字段以 `unknown_N` 命名而非丢弃
- **保活心跳机制**：`AsyncTdxClient` 自动发送心跳包，帮助维持长连接
- **沪深 A 股完整列表**：`get_security_list_all()` 自动过滤非 A 股品种并尽力挂载行业信息
- **北交所列表限制**：`get_security_list(Market.BJ, start)` 当前不能稳定获取，BJ 暂未纳入 `get_security_list_all()`
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

# asyncio 版本同样支持（工厂本身也要 await）
client = await AsyncTdxClient.from_best_host(ping_timeout=5.0)
```

内置服务器列表（`KNOWN_HOSTS`）：

```
180.153.18.170  180.153.18.171  180.153.18.172
124.71.187.122  119.147.212.81
115.238.56.198  115.238.90.165  218.75.126.9
47.107.75.159   59.175.238.38
```

`from_best_host()` 会把测速可达的主机配置为候选列表，但单次调用最多尝试
`max_attempts` 台（默认 2 台）。直接使用 `TdxClient(host)` 且不传
`fallback_hosts` 时，重连仍是同一台主机。


## API

### TdxClient

| 方法 | 说明 |
|------|------|
| `get_security_count(market)` | 市场证券总数 |
| `get_security_list(market, start)` | 证券列表（每页 ~1000 条；BJ 当前不能稳定获取） |
| `get_security_list_all()` | 沪深 A 股列表（尽力挂载行业信息；BJ 暂未纳入） |
| `get_market_stat()` | 全市场 A 股涨跌统计（家数、成交额） |
| `get_security_quotes([(market, code), ...])` | 批量实时五档行情（任意数量，内部每 80 只分片） |
| `get_price_limits(market, code, name, pre_close)` | 计算当前涨跌停价（自动处理上市初期无涨跌幅限制） |
| `get_security_bars(market, code, category, start, count=800)` | K 线（股票） |
| `get_index_bars(market, code, category, start, count=800)` | K 线（指数） |
| `get_bars(market, code, category, start, count=800)` | 按代码自动路由股票/指数 K 线 |
| `get_bars_range(market, code, start_date, end_date, category=DAY)` | 获取日期闭区间 K 线，自动分页、排序和去重 |
| `get_minute_time_data(market, code)` | 今日分时（盘中返回截至当前，全天最多约 240 条） |
| `get_history_minute_time_data(market, code, date)` | 历史某日分时，`date=YYYYMMDD` |
| `get_transaction_data(market, code, start, count=800)` | 当日逐笔成交（分页） |
| `get_history_transaction_data(market, code, date, start, count=800)` | 历史逐笔成交 |
| `get_fund_flow(market, code)` | 当日资金流向统计（800 条分页至结束并校验成交量覆盖） |
| `get_history_fund_flow(market, code, start, count)` | 历史日线资金流向序列（优先 Category 22，空回包时自动回退到历史逐笔重算） |
| `get_xdxr_info(market, code)` | 除权除息历史 |
| `get_finance_info(market, code)` | 最新财务数据 |
| `get_company_info_category(market, code)` | 公司信息文件目录 |
| `get_company_info_content(market, code, filename, offset, length)` | 公司信息文本 |
| `get_block_info(filename)` | 板块信息（行业、概念、风格等） |
| `get_report_file(filename)` | 批量拉取大文件（如 'base_info.zip', 'gpcw.txt'） |

`AsyncTdxClient` 提供与同步版对应的查询方法与高可用入口，均为 `async def`。
单个 `AsyncTdxClient` 仅维护一条 TCP 连接；并发调用会在连接内串行执行。

所有 dataclass 结果可用 `to_dataframe(records)` 转为 DataFrame；需安装
`xmtdx[pandas]`，默认不暴露 `_raw`，调试时可传 `include_raw=True`。

## 已知限制

- `xmtdx` 当前不能稳定获取 BJ 证券列表；`get_security_count(Market.BJ)` 可用，但 `get_security_list(Market.BJ, start)` 经常超时，因此 `get_security_list_all()` 暂不纳入 BJ。
- 公共服务器的逐笔单页按 800 条使用；若返回重复页、分页范围耗尽或逐笔量低于查询前的行情快照成交量，资金流接口会抛出 `TdxResponseError`，不会返回已知不完整的统计。
- `get_history_fund_flow()` 的 Category 22 兼容回退需要历史逐笔数据；服务器对过去交易日返回空数据时会报错，不会把“缺数据”伪装成全零资金流。
- 心跳、重连和候选服务器只能提高可用性，不构成生产环境 SLA；公共服务器地址及行为可能随时变化。

### KlineCategory

```
MIN_1  MIN_1_ALT  MIN_5  MIN_15  MIN_30  MIN_60
DAY  DAY_ALT  WEEK  MONTH  SEASON  YEAR
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
rise_speed  limit_up  limit_down  quote_time
server_time   # 兼容旧名称，0.2.1 起弃用
unknown_0..unknown_8
_raw
```

`limit_up` / `limit_down` 当前不再直接由协议字段映射，默认保留为 `None`；
建议通过 `client.get_price_limits(...)` 计算当前涨跌停价，或用
`xmtdx.codec.price_rules.compute_price_limits(..., listed_days=...)` 做纯规则计算。

`quote_time` 是 `unknown_0` 解码出的单只证券行情快照更新时间，格式为
`HH:MM:SS.mmm`，不含日期，也不是服务器当前墙上时间。同一批证券的值可能不同。
`server_time` 暂时保留相同值以兼容 0.2.0 调用方，请迁移到 `quote_time`。

涨跌停计算使用当前规则：沪深主板 10%，创业板/科创板 20%，北交所 30%；
自 2026-07-06 起沪深主板风险警示股票同样按 10% 处理。该函数不用于还原历史日期规则。

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
num_orders  # 当日逐笔成交笔数；历史接口为 None
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

`category == 1` 时，`fenhong / songzhuangu / peigu` 已归一化为“每股”口径。

### 复权公式

若在仓库外自行计算前复权 / 后复权，建议仅使用 `category == 1` 的 `xdxr`
记录（现金分红 / 送转 / 配股）参与因子计算：

- `cash = fenhong`
- `bonus = songzhuangu`
- `rights = peigu`
- `rights_price = peigujia`

单次除权除息事件的价格因子可写为：

```text
factor = (pre_close - cash + rights * rights_price) / (1 + bonus + rights)
```

其中 `pre_close` 为事件前一交易日的未复权收盘价。

- 前复权：将事件日前的历史价格连续乘以各次 `factor`
- 后复权：将事件日后的价格连续除以各次 `factor`

当前建议只把 `category == 1` 用作复权；`2..14` 类事件仍更适合作为原始事件暴露，
不建议直接纳入通用复权引擎。

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

资金流由 L1 逐笔按单笔金额分档计算，不等同于交易所或商业数据商的官方资金流口径。
当日接口会获取查询开始时的行情成交量作为最低覆盖基线；逐笔可继续更新，因此最终
逐笔总量略高于该快照属于正常情况。

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
| 8 | `index_bars` | 按股票记录长度解析，第二条起字段错位 | 每条额外消费并暴露 `up_count/down_count` |
| 9 | `security_list` | 部分服务器单连接翻页会停滞 | 每页完成后主动换新连接 |
| 10 | `transaction` | 当日 `num_orders` 被丢弃，分页全局去重误删合法同值成交 | 保留笔数，只消除相邻页边界重叠 |
| 11 | `fund_flow` | 请求 2000 条导致服务器短页/空页并提前结束，只统计尾盘 | 固定 800 条倒序翻页至空页，检测停滞并校验成交量覆盖 |

## 使用边界

xmtdx 是对未公开行情协议的兼容性逆向实现，仅供研究和技术验证。使用者应自行确认
数据来源、服务条款、授权和再分发要求。公共服务器不保证永久开放、数据完整、实时性
或适合交易用途；任何交易决策都应使用具备相应授权和服务保障的数据源复核。

## 架构

```
src/xmtdx/
├── client.py          # TdxClient / AsyncTdxClient（高层 API）
├── transport/
│   ├── sync.py        # TdxConnection（socket）+ ping_host / ping_all
│   ├── async_.py      # AsyncTdxConnection（asyncio）
│   └── capture.py     # 请求/帧头/压缩体/解压体的诊断捕获
├── commands/          # 每条命令：build_request() + parse_response()，无 IO
├── codec/             # price / volume / datetime / frame 编解码
├── models/            # 纯 dataclass，无业务逻辑
├── validation.py      # 参数与响应语义校验
└── dataframe.py       # 可选 pandas 适配
```

commands 层不依赖 transport，可独立单测。transport 层负责 TCP、握手、帧解压、分发。

## 开发

```bash
# 单元测试（无需网络）
python -m pytest tests/unit/

# 集成测试（需要网络，默认跳过）
XMTDX_LIVE=1 python -m pytest tests/integration/

# 较完整的在线能力矩阵（JSON 输出）
python scripts/validate_live.py --json

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

各命令的支持和验证状态见 [协议覆盖矩阵](docs/protocol-coverage.md)。在线行情会受交易时段、服务器版本、标的停牌和服务器临时故障影响；“解析已覆盖”不等于任何时刻每台公共服务器都可用。
