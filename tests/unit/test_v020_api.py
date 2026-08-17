"""0.2.0 协议修正与高层 API 回归测试。"""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from xmtdx import KlineCategory, Market, TdxClient, to_dataframe
from xmtdx.client import _boundary_overlap, _validate_bars
from xmtdx.codec.price import put_price
from xmtdx.commands.finance_info import GetFinanceInfoCmd
from xmtdx.commands.security_bars import GetIndexBarsCmd
from xmtdx.commands.security_quotes import GetSecurityQuotesCmd
from xmtdx.commands.transaction import GetTransactionDataCmd
from xmtdx.exceptions import TdxResponseError
from xmtdx.models.bar import IndexBar, SecurityBar
from xmtdx.models.timeseries import TransactionRecord
from xmtdx.validation import validate_code, validate_date, validate_filename

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _index_record(
    date: int,
    open_diff: int,
    close_diff: int,
    high_diff: int,
    low_diff: int,
    up_count: int,
    down_count: int,
) -> bytes:
    return b"".join(
        (
            struct.pack("<I", date),
            put_price(open_diff),
            put_price(close_diff),
            put_price(high_diff),
            put_price(low_diff),
            b"\x00" * 8,
            struct.pack("<HH", up_count, down_count),
        )
    )


def _bar(date: int, price: float = 10.0) -> SecurityBar:
    return SecurityBar(
        price, price, price, price, 1.0, 1.0,
        date // 10000, (date // 100) % 100, date % 100, 15, 0,
    )


def test_index_bars_parse_breadth_without_losing_record_alignment() -> None:
    body = struct.pack("<H", 2)
    body += _index_record(20260814, 100_000, 1_000, 2_000, -1_000, 3210, 1900)
    body += _index_record(20260815, 500, -500, 1_000, -1_500, 3000, 2100)

    bars = GetIndexBarsCmd(
        Market.SH, "000001", KlineCategory.DAY, 0, 2
    ).parse_response(body)

    assert [(bar.year, bar.month, bar.day) for bar in bars] == [
        (2026, 8, 14),
        (2026, 8, 15),
    ]
    assert [(bar.open, bar.close) for bar in bars] == [(100.0, 101.0), (101.5, 101.0)]
    assert [(bar.up_count, bar.down_count) for bar in bars] == [(3210, 1900), (3000, 2100)]
    assert all(isinstance(bar, IndexBar) for bar in bars)


def test_current_transaction_retains_num_orders() -> None:
    body = bytes.fromhex((FIXTURES / "transaction.hex").read_text().strip())
    records = GetTransactionDataCmd(Market.SH, "600000", 0, 800).parse_response(body)
    assert records
    assert all(record.num_orders is not None for record in records)


def test_quote_and_finance_reject_mismatched_security() -> None:
    quote_body = bytes.fromhex((FIXTURES / "security_quotes.hex").read_text().strip())
    with pytest.raises(TdxResponseError, match="不匹配"):
        GetSecurityQuotesCmd([(Market.SZ, "000001")]).parse_response(quote_body)

    finance_body = bytes.fromhex((FIXTURES / "finance_info.hex").read_text().strip())
    with pytest.raises(TdxResponseError, match="不匹配"):
        GetFinanceInfoCmd(Market.SZ, "000001").parse_response(finance_body)


def test_corrected_kline_category_values() -> None:
    assert KlineCategory.MIN_1_ALT == 8
    assert KlineCategory.DAY_ALT == 9
    assert KlineCategory.SEASON == 10
    assert KlineCategory.YEAR == 11
    assert not hasattr(KlineCategory, "MIN_3")
    assert not hasattr(KlineCategory, "YEAR_ALT")


def test_public_argument_validation() -> None:
    for invalid in ("60000", "ABCDEF", "６０００００"):
        with pytest.raises(ValueError):
            validate_code(invalid)
    with pytest.raises(ValueError):
        validate_date(20260230)
    with pytest.raises(ValueError):
        validate_date(202681)
    with pytest.raises(ValueError):
        validate_filename("bad\x00name", 100, "ascii")


def test_bar_semantic_validation_detects_corruption() -> None:
    bad_date = _bar(19890101)
    with pytest.raises(TdxResponseError, match="日期非法"):
        _validate_bars([bad_date], "test")

    bad_ohlc = _bar(20260814)
    bad_ohlc.high = 9.0
    with pytest.raises(TdxResponseError, match="最高价"):
        _validate_bars([bad_ohlc], "test")


@patch("xmtdx.client.TdxConnection")
def test_quotes_are_automatically_batched(_connection: object) -> None:
    client = TdxClient("127.0.0.1")
    sizes: list[int] = []

    def execute(command: object) -> list[object]:
        sizes.append(len(command.stocks))  # type: ignore[attr-defined]
        return []

    with patch.object(client, "_execute", side_effect=execute):
        result = client.get_security_quotes(
            [(Market.SH, f"{index:06d}") for index in range(161)]
        )
    assert result == []
    assert sizes == [80, 80, 1]


@patch("xmtdx.client.TdxConnection")
def test_get_bars_routes_and_range_pages(_connection: object) -> None:
    client = TdxClient("127.0.0.1")
    with patch.object(client, "get_index_bars", return_value=[]) as index, patch.object(
        client, "get_security_bars", return_value=[]
    ) as stock:
        assert client.get_bars(Market.SH, "000001", KlineCategory.DAY, 0) == []
        assert client.get_bars(Market.SH, "600000", KlineCategory.DAY, 0) == []
        index.assert_called_once()
        stock.assert_called_once()

    pages = [[_bar(20260201)] * 800, [_bar(20260115), _bar(20251231)]]
    with patch.object(client, "get_bars", side_effect=pages):
        ranged = client.get_bars_range(Market.SH, "600000", 20260101, 20260228)
    assert [(bar.year, bar.month, bar.day) for bar in ranged] == [
        (2026, 1, 15),
        (2026, 2, 1),
    ]


def test_transaction_overlap_only_removes_page_boundary() -> None:
    a = TransactionRecord(9, 30, 10.0, 1, 0, 0)
    b = TransactionRecord(9, 31, 10.0, 1, 0, 0)
    assert _boundary_overlap([a, b], [b, b]) == 1
    assert _boundary_overlap([a, b], [a, b]) == 2


def test_to_dataframe_excludes_raw_by_default() -> None:
    frame = to_dataframe([_bar(20260814)])
    assert "_raw" not in frame.columns
    assert frame.iloc[0]["year"] == 2026
    with pytest.raises(TypeError):
        to_dataframe([object()])


def test_async_quote_batching() -> None:
    from xmtdx import AsyncTdxClient

    async def main() -> None:
        client = AsyncTdxClient("127.0.0.1", heartbeat_interval=0)
        sizes: list[int] = []

        async def execute(command: object) -> list[object]:
            sizes.append(len(command.stocks))  # type: ignore[attr-defined]
            return []

        with patch.object(client, "_execute", side_effect=execute):
            result = await client.get_security_quotes(
                [(Market.SH, f"{index:06d}") for index in range(81)]
            )
        assert result == []
        assert sizes == [80, 1]

    asyncio.run(main())


def test_sync_response_error_rotates_to_fallback_host() -> None:
    first = MagicMock()
    first.is_connected = False
    first.execute.side_effect = TdxResponseError("mismatch")
    second = MagicMock()
    second.is_connected = False
    second.execute.return_value = 123

    with patch("xmtdx.client.TdxConnection", side_effect=[first, second]):
        client = TdxClient(
            "primary", fallback_hosts=["fallback"], max_attempts=2
        )
        assert client.get_security_count(Market.SH) == 123

    first.close.assert_called()
    second.connect.assert_called_once()
    assert client._host == "fallback"


def test_async_response_error_rotates_to_fallback_host() -> None:
    from xmtdx import AsyncTdxClient

    async def main() -> None:
        first = MagicMock()
        first.is_connected = False
        first.connect = AsyncMock()
        first.close = AsyncMock()
        first.execute = AsyncMock(side_effect=TdxResponseError("mismatch"))
        second = MagicMock()
        second.is_connected = False
        second.connect = AsyncMock()
        second.close = AsyncMock()
        second.execute = AsyncMock(return_value=456)

        with patch("xmtdx.client.AsyncTdxConnection", side_effect=[first, second]):
            client = AsyncTdxClient(
                "primary",
                fallback_hosts=["fallback"],
                max_attempts=2,
                heartbeat_interval=0,
            )
            assert await client.get_security_count(Market.SH) == 456
            await client.close()

        assert client._host == "fallback"
        second.connect.assert_awaited_once()

    asyncio.run(main())
