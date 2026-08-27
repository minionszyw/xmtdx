# 7709 行情协议覆盖矩阵

状态含义：`已验证` 表示有离线夹具/构造包测试且经过真实服务器抽查；`受限` 表示解析可用，但公共服务器端行为不稳定或字段语义尚未完全确认。

| 能力 | 命令/API | 状态 | 说明 |
|---|---|---|---|
| 市场证券数 | `get_security_count` | 已验证 | SH/SZ/BJ 均可查询 |
| 证券列表 | `get_security_list` | 受限 | SH/SZ 可分页；部分主机要求每页新连接；BJ 列表不稳定 |
| 沪深 A 股全集 | `get_security_list_all` | 已验证 | 自动分页、过滤并尝试挂载行业；不含 BJ |
| 五档行情 | `get_security_quotes` | 已验证 | 单包上限 80；`quote_time` 是单证券快照更新时间，并非服务器墙上时间 |
| 股票 K 线 | `get_security_bars` | 已验证 | 单次最多 800，校验日期/OHLC/量额 |
| 指数 K 线 | `get_index_bars` | 已验证 | 独立记录布局，含 `up_count/down_count` |
| 自动/区间 K 线 | `get_bars` / `get_bars_range` | 已验证 | 自动路由、分页、闭区间过滤、排序去重 |
| 今日分时 | `get_minute_time_data` | 受限 | 非交易时段优先返回空；异常价格通过行情/最新日线交叉校验 |
| 历史分时 | `get_history_minute_time_data` | 已验证 | 有效交易日可用 |
| 当日逐笔 | `get_transaction_data` | 已验证 | 单页上限按 800 使用；服务器按最新到更早分页 |
| 历史逐笔 | `get_history_transaction_data` | 已验证 | 单页上限 800；`num_orders=None`；当天盘中可能返回空 |
| 除权除息 | `get_xdxr_info` | 已验证 | 核对返回证券，股本类仍以万股暴露 |
| 财务数据 | `get_finance_info` | 已验证 | 核对返回证券；股本统一为股，金额统一为元 |
| 公司资料 | `get_company_info_*` | 已验证 | 目录及按偏移文本读取 |
| 板块文件 | `get_block_info` | 已验证 | 校验长度；服务器提供 32 位哈希时校验 MD5 |
| 报表文件 | `get_report_file` | 受限 | 检测重复分片；部分主机的 `base_info.zip` 返回空 |
| 市场涨跌统计 | `get_market_stat` | 受限 | `880005` 映射；停牌数是守恒残差，不是已确认协议字段 |
| 资金流 | `get_fund_flow` / `get_history_fund_flow` | 受限 | L1 逐笔金额分档；当日校验成交量覆盖；缺失/停滞时拒绝返回部分值 |

## 诊断捕获

底层同步和异步连接均提供 `capture(command)`，返回 `CapturedResponse`：

- `request`：完整请求包；
- `header`：16 字节响应帧头的结构化结果；
- `raw_body`：服务器传回的压缩/原始负载；
- `body`：解压后的命令负载；
- `result`：命令解析结果。

这些字节适合脱敏后固化为离线回归夹具。不要把包含账号、授权或其他敏感信息的私有抓包提交到仓库；xmtdx 当前覆盖的 7709 行情查询本身不需要账户登录。

## 明确不在范围内

- 扩展行情/期货等 ExHQ 协议；
- 交易、委托、账户登录协议；
- 保证第三方公共服务器永久在线或行为一致；
- 将尚未确认的 `unknown_N` 字段强行命名。
