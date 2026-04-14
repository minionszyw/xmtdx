"""财务与公司信息模型"""

from dataclasses import dataclass, field

from .enums import Market


@dataclass
class XdxrRecord:
    """除权除息记录（一只股票可有多条）

    pytdx Bug #1 已修复：循环内不再从 body[:7] 读 market/code，
    而是从当前 pos 正确读取。
    """

    market: Market
    code: str
    year: int
    month: int
    day: int
    category: int   # 事件类型（见下方 CATEGORY_NAMES）
    name: str       # 事件类型名称

    # category == 1（除权除息）
    fenhong: float | None = None      # 每股分红（元）
    peigujia: float | None = None     # 配股价（元）
    songzhuangu: float | None = None  # 送转股比例
    peigu: float | None = None        # 配股比例

    # category in [11, 12]（扩缩股）
    suogu: float | None = None        # 缩股比例

    # category in [13, 14]（权证）
    xingquanjia: float | None = None  # 行权价
    fenshu: float | None = None       # 分数

    # category in [2..10]（股本变动类，单位：万股）
    panqian_liutong: float | None = None   # 盘前流通股本（万股）
    panhou_liutong: float | None = None    # 盘后流通股本（万股）
    qian_zongguben: float | None = None    # 前总股本（万股）
    hou_zongguben: float | None = None     # 后总股本（万股）

    _raw: bytes = field(default=b"", repr=False, compare=False)


XDXR_CATEGORY_NAMES: dict[int, str] = {
    1: "除权除息",
    2: "送配股上市",
    3: "非流通股上市",
    4: "未知股本变动",
    5: "股本变化",
    6: "增发新股",
    7: "股份回购",
    8: "增发新股上市",
    9: "转配股上市",
    10: "可转债上市",
    11: "扩缩股",
    12: "非流通股缩股",
    13: "送认购权证",
    14: "送认沽权证",
}


@dataclass
class FinanceInfo:
    """最新财务数据（单只股票）"""

    market: Market
    code: str

    # 股本（万股）
    liutong_guben: float    # 流通股本
    zong_guben: float       # 总股本
    guojia_gu: float        # 国家股
    faqiren_faren_gu: float  # 发起人法人股
    faren_gu: float         # 法人股
    b_gu: float             # B股
    h_gu: float             # H股
    zhigong_gu: float       # 职工股

    # 基本信息
    province: int           # 所属省份代码
    industry: int           # 所属行业代码
    updated_date: int       # 财务更新日期 YYYYMMDD
    ipo_date: int           # 上市日期 YYYYMMDD
    gudong_renshu: float    # 股东人数

    # 资产负债（元）
    zong_zichan: float       # 总资产
    liudong_zichan: float    # 流动资产
    guding_zichan: float     # 固定资产
    wuxing_zichan: float     # 无形资产
    liudong_fuzhai: float    # 流动负债
    changqi_fuzhai: float    # 长期负债
    ziben_gongjijin: float   # 资本公积金
    jing_zichan: float       # 净资产

    # 利润（元）
    zhuying_shouru: float    # 主营收入
    zhuying_lirun: float     # 主营利润
    yingshou_zhangkuan: float  # 应收账款
    yingye_lirun: float      # 营业利润
    touzi_shouyu: float      # 投资收益
    jingying_xianjinliu: float  # 经营现金流
    zong_xianjinliu: float   # 总现金流
    cunhuo: float            # 存货
    lirun_zonghe: float      # 利润总额
    shuihou_lirun: float     # 税后利润
    jing_lirun: float        # 净利润
    weifen_lirun: float      # 未分配利润

    # 每股指标
    meigujing_zichan: float  # 每股净资产（原 baoliu1）

    # 协议保留字段（含义未完全确认）
    reserve2: float = field(default=0.0, repr=False)  # 原 baoliu2

    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class CompanyInfoCategory:
    """公司信息文件目录条目"""

    name: str = ""      # 目录名（如“最新提示”）
    filename: str = ""  # 文件名（如 '600000.txt'）
    start: int = 0      # 内容起始偏移
    length: int = 0     # 内容长度（字节）


@dataclass
class TdxBlock:
    """通达信板块信息（行业、概念、风格等）"""

    name: str           # 板块名称（如“房地产”）
    category: int       # 板块分类（0=行业, 1=地域, 2=概念, 3=风格, 等）
    count: int          # 板块包含股票数量
    codes: list[str]    # 股票代码列表（6位数字代码）
