"""对真实 7709 行情服务器执行可重复的能力矩阵验证。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from xmtdx import AsyncTdxClient, KlineCategory, Market, TdxClient
from xmtdx.transport.sync import KNOWN_HOSTS


def _date(bar: Any) -> int:
    return bar.year * 10000 + bar.month * 100 + bar.day


def _require(value: Any, message: str) -> Any:
    if not value:
        raise RuntimeError(message)
    return value


def _run_check(report: dict[str, Any], name: str, operation: Callable[[], Any]) -> Any:
    started = time.monotonic()
    try:
        value = operation()
        size = len(value) if hasattr(value, "__len__") else None
        report[name] = {
            "ok": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "size": size,
        }
        return value
    except Exception as error:
        report[name] = {
            "ok": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": f"{type(error).__name__}: {error}",
        }
        return None


async def _validate_async(hosts: list[str], timeout: float) -> dict[str, Any]:
    report: dict[str, Any] = {}
    started = time.monotonic()
    try:
        client = await AsyncTdxClient.from_best_host(
            hosts, timeout=timeout, ping_timeout=timeout, heartbeat_interval=0
        )
        try:
            count = await client.get_security_count(Market.SH)
            bars = await client.get_bars(
                Market.SH, "600000", KlineCategory.DAY, 0, 2
            )
            report["async_core"] = {
                "ok": count > 0 and bool(bars),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "count": count,
                "bars": len(bars),
            }
        finally:
            await client.close()
    except Exception as error:
        report["async_core"] = {
            "ok": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": f"{type(error).__name__}: {error}",
        }
    return report


def validate(hosts: list[str], timeout: float, full_list: bool, quick: bool) -> dict[str, Any]:
    report: dict[str, Any] = {"hosts": hosts, "checks": {}}
    checks: dict[str, Any] = report["checks"]
    ranked = _run_check(checks, "host_probe", lambda: TdxClient.ping_all(hosts, 7709, timeout))
    ordered = [host for host, _latency in ranked] if ranked else hosts
    if not ordered:
        return report

    client = TdxClient(
        ordered[0], timeout=timeout, fallback_hosts=ordered[1:], max_attempts=len(ordered)
    )
    try:
        for market in Market:
            _run_check(
                checks,
                f"security_count_{market.name.lower()}",
                lambda market=market: _require(
                    client.get_security_count(market), "证券数量为 0"
                ),
            )

        if full_list:
            _run_check(checks, "security_list_all", client.get_security_list_all)

        _run_check(
            checks,
            "quotes_sh_sz_bj",
            lambda: _require(
                client.get_security_quotes(
                    [
                        (Market.SH, "600000"),
                        (Market.SZ, "000001"),
                        (Market.BJ, "920002"),
                    ]
                ),
                "行情为空",
            ),
        )
        stock_bars = _run_check(
            checks,
            "stock_bars_all_categories",
            lambda: _require(
                {
                    category.name: _require(
                        client.get_security_bars(
                            Market.SH, "600000", category, 0, 2
                        ),
                        f"{category.name} K 线为空",
                    )
                    for category in KlineCategory
                },
                "K 线为空",
            ),
        )
        _run_check(
            checks,
            "index_bars",
            lambda: _require(
                client.get_index_bars(
                    Market.SH, "000001", KlineCategory.DAY, 0, 5
                ),
                "指数 K 线为空",
            ),
        )

        daily = stock_bars.get("DAY") if stock_bars else None
        latest_date = _date(daily[-1]) if daily else None
        today = int(datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"))
        history_date = latest_date
        if daily and latest_date == today and len(daily) > 1:
            history_date = _date(daily[-2])
        _run_check(
            checks,
            "minute_current",
            lambda: client.get_minute_time_data(Market.SH, "600000"),
        )
        if history_date:
            _run_check(
                checks,
                "minute_history",
                lambda: _require(
                    client.get_history_minute_time_data(
                        Market.SH, "600000", history_date
                    ),
                    "历史分时为空",
                ),
            )
            _run_check(
                checks,
                "transaction_history",
                lambda: _require(
                    client.get_history_transaction_data(
                        Market.SH, "600000", history_date, 0, 20
                    ),
                    "历史逐笔为空",
                ),
            )
        _run_check(
            checks,
            "transaction_current",
            lambda: _require(
                client.get_transaction_data(Market.SH, "600000", 0, 20),
                "当日逐笔为空",
            ),
        )
        _run_check(checks, "finance", lambda: client.get_finance_info(Market.SH, "600000"))
        _run_check(checks, "xdxr", lambda: client.get_xdxr_info(Market.SH, "600000"))

        categories = _run_check(
            checks,
            "company_categories",
            lambda: _require(
                client.get_company_info_category(Market.SH, "600000"),
                "公司资料目录为空",
            ),
        )
        if categories:
            first = categories[0]
            _run_check(
                checks,
                "company_content",
                lambda: client.get_company_info_content(
                    Market.SH,
                    "600000",
                    first.filename,
                    first.start,
                    min(first.length, 4096),
                ),
            )

        _run_check(checks, "market_stat", client.get_market_stat)
        if not quick:
            _run_check(
                checks,
                "block_info",
                lambda: _require(client.get_block_info("block_gn.dat"), "板块文件为空"),
            )
            _run_check(
                checks,
                "report_file",
                lambda: _require(client.get_report_file("tdxhy.cfg"), "报表文件为空"),
            )
            _run_check(
                checks,
                "fund_flow_current",
                lambda: client.get_fund_flow(Market.SH, "600000"),
            )
            _run_check(
                checks,
                "fund_flow_history",
                lambda: client.get_history_fund_flow(Market.SH, "600000", 0, 1),
            )
    finally:
        client.close()

    checks.update(asyncio.run(_validate_async(ordered, timeout)))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="append", dest="hosts", help="候选服务器，可重复")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--full-list", action="store_true", help="额外扫描沪深 A 股完整列表")
    parser.add_argument("--quick", action="store_true", help="跳过文件下载和资金流等耗时检查")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = validate(args.hosts or KNOWN_HOSTS, args.timeout, args.full_list, args.quick)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for name, result in report["checks"].items():
            marker = "PASS" if result["ok"] else "FAIL"
            detail = result.get("error", f"{result.get('elapsed_ms')} ms")
            print(f"{marker:4} {name:30} {detail}")
    return 0 if all(item["ok"] for item in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
