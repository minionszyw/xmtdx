"""针对本轮 A 股增强功能的单元测试。"""

import struct
from unittest.mock import patch

from xmtdx import Market, TdxClient
from xmtdx.models.quote import SecurityQuote
from xmtdx.models.security import SecurityInfo
from xmtdx.models.timeseries import TransactionRecord


@patch("xmtdx.client.TdxConnection")
def test_get_fund_flow_logic(_mock_conn_cls):
    """测试资金流分类计算逻辑。"""
    client = TdxClient("127.0.0.1")
    
    # 构造模拟 Tick 数据
    mock_recs = [
        TransactionRecord(10, 0, 100.0, 100, 0, 0), # super_in (100*100*100 = 100w)
        TransactionRecord(10, 1, 10.0, 250, 1, 0),  # large_out (10*250*100 = 25w)
        TransactionRecord(10, 2, 10.0, 10, 0, 0),   # small_in (10*10*100 = 1w)
    ]
    
    with patch.object(TdxClient, "get_transaction_data", return_value=mock_recs):
        flow = client.get_fund_flow(Market.SH, "600000")
        
        assert flow.super_in == 1000000.0
        assert flow.large_out == 250000.0
        assert flow.small_in == 10000.0
        assert flow.main_net_inflow == 1000000.0 - 250000.0

@patch("xmtdx.client.TdxConnection")
def test_get_security_list_all_filtering(_mock_conn_cls):
    """测试三市 A 股过滤与行业挂载逻辑。"""
    client = TdxClient("127.0.0.1")
    
    # 模拟行业配置 tdxhy.cfg
    industry_cfg = b"1|600000|T01|||X01\n0|000001|T02|||X02\n2|830000|T03|||X03"
    
    # 模拟各市场返回
    def mock_get_list(market, start):
        if market == Market.SH:
            return [
                SecurityInfo(Market.SH, "600000", "SH_A", 100, 2, 10.0),
                SecurityInfo(Market.SH, "999999", "INDEX", 100, 2, 3000.0), # 应被过滤
            ]
        if market == Market.SZ:
            return [SecurityInfo(Market.SZ, "000001", "SZ_A", 100, 2, 10.0)]
        if market == Market.BJ:
            return [SecurityInfo(Market.BJ, "830000", "BJ_A", 100, 2, 10.0)]
        return []

    with patch.object(TdxClient, "get_report_file", return_value=industry_cfg), \
         patch.object(TdxClient, "get_security_count", return_value=1), \
         patch.object(TdxClient, "get_security_list", side_effect=mock_get_list):
        
        all_stocks = client.get_security_list_all()

        # 预期只有 SH 和 SZ，BJ 已在扫描中降级移除
        assert len(all_stocks) == 2
        codes = [s.code for s in all_stocks]
        assert "600000" in codes
        assert "000001" in codes
        assert "830000" not in codes        
        s0 = next(s for s in all_stocks if s.code == "600000")
        assert s0.industry_tdx == "T01"

@patch("xmtdx.client.TdxConnection")
def test_get_market_stat_mapping(_mock_conn_cls):
    """测试市场统计字段映射。"""
    client = TdxClient("127.0.0.1")
    
    mock_quote = SecurityQuote(
        Market.SH, "880005",
        price=3000.0,      # up
        pre_close=2000.0,  # down
        open=0,
        high=5500.0,       # total
        low=500.0,         # neutral (low=500 -> neutral_count=500)
        vol=1000000.0, cur_vol=0, amount=50000000.0,
        s_vol=0, b_vol=0, active1=0, active2=0,
        bid1=0, bid_vol1=0, bid2=0, bid_vol2=0, bid3=0, bid_vol3=0,
        bid4=0, bid_vol4=0, bid5=0, bid_vol5=0,
        ask1=0, ask_vol1=0, ask2=0, ask_vol2=0, ask3=0, ask_vol3=0,
        ask4=0, ask_vol4=0, ask5=0, ask_vol5=0,
        rise_speed=0, limit_up=0, limit_down=0
    )
    
    with patch.object(TdxClient, "get_security_quotes", return_value=[mock_quote]):
        stat = client.get_market_stat()
        assert stat.up_count == 3000
        assert stat.down_count == 2000
        assert stat.neutral_count == 500
        assert stat.total_count == 5500

def test_get_history_fund_flow_parsing():
    """测试历史资金流序列解析逻辑。"""
    from xmtdx.commands.fund_flow import GetHistoryFundFlowCmd
    
    # 模拟 Category 22 响应 (Header 9 + Count 2 + Body 36)
    body = bytearray(9)
    body.extend(struct.pack("<H", 1)) # 1 record
    
    # Record: Date(I) + 8 * custom_float(i)
    # 2025-01-08
    date = 20250108
    # 模拟 8 个流向金额
    record = struct.pack("<Iiiiiiiii", date, 100, 200, 300, 400, 500, 600, 700, 800)
    body.extend(record)
    
    cmd = GetHistoryFundFlowCmd(Market.SH, "600000", 0, 1)
    res = cmd.parse_response(bytes(body))
    
    assert len(res) == 1
    assert res[0].year == 2025
    assert res[0].month == 1
    assert res[0].day == 8
