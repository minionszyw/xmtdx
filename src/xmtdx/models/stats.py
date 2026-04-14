"""验证市场概况模型。"""
from dataclasses import dataclass

@dataclass
class MarketStat:
    """全市场涨跌统计概况。"""
    up_count: int       # 上涨家数
    down_count: int     # 下跌家数
    neutral_count: int  # 平盘家数
    total_count: int    # 总家数
    total_amount: float # 总成交额
    total_volume: float # 总成交量
