"""协议底层修复验证（针对 2026-04-15 审查结论）。"""

import struct
from unittest.mock import patch

from xmtdx.codec.price_rules import compute_price_limits
from xmtdx.commands.fund_flow import GetHistoryFundFlowCmd
from xmtdx.commands.security_bars import GetSecurityBarsCmd
from xmtdx.commands.security_list import GetSecurityListCmd
from xmtdx.commands.security_quotes import GetSecurityQuotesCmd
from xmtdx.models.enums import KlineCategory, Market


def test_security_bars_exact_layout():
    """验证 K 线请求包布局与旧版 working bytes 完全一致。"""
    cmd = GetSecurityBarsCmd(Market.SH, "600000", KlineCategory.DAY, 0, 10)
    req = cmd.build_request()
    # Header: 0x010C, 0x01016408, 0x1C, 0x1C
    # Payload: 0x052D, 1 (Market.SH), "600000", 4 (KlineCategory.DAY), 1, 0 (start), 10, 0, 0, 0
    expected = struct.pack(
        "<HIHHHH6sHHHHIIH",
        0x010C, 0x01016408, 0x001C, 0x001C,
        0x052D, 1, b"600000", 4, 1, 0, 10, 0, 0, 0
    )
    assert req == expected
    assert len(req) == 38


def test_history_fund_flow_exact_layout():
    """验证历史资金流请求包布局与 K 线一致，只差 category=22。"""
    cmd = GetHistoryFundFlowCmd(Market.SH, "600000", 0, 10)
    req = cmd.build_request()
    # Header: 0x010C, 0x01016408, 0x1C, 0x1C
    # Payload: 0x052D, 1 (Market.SH), "600000", 22, 1, 0, 10, 0, 0, 0
    expected = struct.pack(
        "<HIHHHH6sHHHHIIH",
        0x010C, 0x01016408, 0x001C, 0x001C,
        0x052D, 1, b"600000", 22, 1, 0, 10, 0, 0, 0
    )
    assert req == expected
    assert len(req) == 38


def test_security_list_request_length():
    """验证证券列表请求包载荷长度为 6 字节。"""
    cmd = GetSecurityListCmd(Market.SH, 0)
    req = cmd.build_request()
    # Header 12 + Payload 6 = 18
    assert len(req) == 18
    payload_len = struct.unpack("<H", req[6:8])[0]
    assert payload_len == 6


def test_security_quotes_limit_mapping():
    """验证涨跌停价现在返回 None，且 pre_close 正确。"""
    from xmtdx.codec.price import put_price

    cmd = GetSecurityQuotesCmd([(Market.SH, "600000")])
    
    # 构造响应报文
    body = bytearray(b"\x00\x00")
    body.extend(struct.pack("<H", 1))
    
    # Record: Market(B), Code(6s), Active1(H) + ...
    body.extend(struct.pack("<B6sH", 1, b"600000", 0))
    
    body.extend(put_price(1010))  # price_raw
    body.extend(put_price(-5))    # last_close_diff
    body.extend(put_price(0))
    body.extend(put_price(0))
    body.extend(put_price(0))
    body.extend(put_price(12345))
    body.extend(put_price(-1010))
    body.extend(put_price(100))
    body.extend(put_price(10))
    body.extend(struct.pack("<I", 10000))
    body.extend(put_price(50))
    body.extend(put_price(50))
    body.extend(put_price(2))
    body.extend(put_price(3))
    for _ in range(20):
        body.extend(put_price(0))
    body.extend(struct.pack("<H", 0))
    body.extend(put_price(96))
    body.extend(put_price(-106))
    body.extend(put_price(0))
    body.extend(put_price(0))
    body.extend(struct.pack("<hH", 0, 0))
    
    quotes = cmd.parse_response(bytes(body))
    q = quotes[0]
    assert q.limit_up is None
    assert q.limit_down is None
    assert q.pre_close == 10.05


def test_security_quotes_server_time_format():
    """服务器时间应按“小时 + 百万分之一小时”统一解码。"""
    from xmtdx.commands.security_quotes import _format_server_time

    assert _format_server_time(9500000) == "09:30:00.000"
    assert _format_server_time(14999212) == "14:59:57.163"


def test_compute_price_limits_for_stocks():
    """普通股票 / ST / 创业板 / 科创板 / 北交所规则应可正确计算。"""
    assert compute_price_limits(Market.SH, "600000", "浦发银行", 10.05) == (11.06, 9.05)
    assert compute_price_limits(Market.SH, "603939", "ST益丰", 22.53) == (23.66, 21.4)
    assert compute_price_limits(Market.SZ, "301269", "华大九天", 86.36) == (103.63, 69.09)
    assert compute_price_limits(Market.SH, "688981", "中芯国际", 101.52) == (121.82, 81.22)
    assert compute_price_limits(Market.BJ, "920002", "万达轴承", 84.36) == (109.67, 59.05)


def test_compute_price_limits_for_indices():
    """指数与板块类代码不应计算涨跌停。"""
    assert compute_price_limits(Market.SH, "999999", "上证指数", 4026.63) == (None, None)
    assert compute_price_limits(Market.SH, "880005", "涨跌家数", 1841.0) == (None, None)
    assert compute_price_limits(Market.SZ, "399001", "深证成指", 10412.63) == (None, None)


def test_compute_price_limits_for_newly_listed_stocks():
    """上市初期限价窗口应返回 None。"""
    assert compute_price_limits(
        Market.SH, "600001", "主板新股", 10.0, listed_days=5
    ) == (None, None)
    assert compute_price_limits(
        Market.SH, "600001", "主板新股", 10.0, listed_days=6
    ) == (11.0, 9.0)
    assert compute_price_limits(
        Market.BJ, "920002", "北交所新股", 84.36, listed_days=1
    ) == (None, None)
    assert compute_price_limits(
        Market.BJ, "920002", "北交所新股", 84.36, listed_days=2
    ) == (109.67, 59.05)


def test_history_fund_flow_uses_uint32_volume_words():
    """历史资金流金额字段必须按 uint32 传给 _decode_volume。"""
    raw_words = [
        0x80000001,
        0xFFFFFFFF,
        0x7FFFFFFF,
        0x90000000,
        0xA0000000,
        0xB0000000,
        0xC0000000,
        0xD0000000,
    ]
    body = bytearray(9)
    body.extend(struct.pack("<H", 1))
    body.extend(struct.pack("<IIIIIIIII", 20250108, *raw_words))

    seen: list[int] = []

    def fake_decode(raw: int) -> float:
        seen.append(raw)
        return float(raw)

    with patch("xmtdx.commands.fund_flow._decode_volume", side_effect=fake_decode):
        records = GetHistoryFundFlowCmd(Market.SH, "600000", 0, 1).parse_response(bytes(body))

    assert seen == raw_words
    assert records[0].small_out == float(raw_words[-1])
