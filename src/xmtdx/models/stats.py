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


@dataclass
class FundFlow:
    """个股资金流向统计（基于 Tick 数据加权计算）。"""
    
    # 流入项 (Buy)
    super_in: float   # 超大单流入 (>100万)
    large_in: float   # 大单流入 (20万-100万)
    medium_in: float  # 中单流入 (4万-20万)
    small_in: float   # 小单流入 (<4万)
    
    # 流出项 (Sell)
    super_out: float
    large_out: float
    medium_out: float
    small_out: float
    
    @property
    def main_net_inflow(self) -> float:
        """主力净流入 (超大单 + 大单)。"""
        return (self.super_in + self.large_in) - (self.super_out + self.large_out)
    
    @property
    def total_net_inflow(self) -> float:
        """全单净流入。"""
        return (self.super_in + self.large_in + self.medium_in + self.small_in) - \
               (self.super_out + self.large_out + self.medium_out + self.small_out)


@dataclass
class HistoricalFundFlow:
    """历史日线资金流向条目。"""
    
    year: int
    month: int
    day: int
    
    # 金额项 (单位：元)
    super_in: float
    super_out: float
    large_in: float
    large_out: float
    medium_in: float
    medium_out: float
    small_in: float
    small_out: float
    
    @property
    def main_net_inflow(self) -> float:
        """当日主力净流入。"""
        return (self.super_in + self.large_in) - (self.super_out + self.large_out)
