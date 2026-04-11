"""最新财务数据命令。"""

import struct

from ..models.enums import Market
from ..models.finance import FinanceInfo
from .base import BaseCommand

# 财务字段 struct 格式：1f + 2H + 2I + 30f
_FIN_FMT = "<fHHII" + "f" * 30
_FIN_SIZE = struct.calcsize(_FIN_FMT)


class GetFinanceInfoCmd(BaseCommand[FinanceInfo]):
    """获取单只股票最新财务数据。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c1f18760001 0b000b001000 0100".replace(" ", ""))
        return header + struct.pack("<B6s", int(self.market), self.code)

    def parse_response(self, body: bytes) -> FinanceInfo:
        pos = 2  # 跳过前2字节（记录数）
        market_b, code_b = struct.unpack_from("<B6s", body, pos)
        pos += 7

        fields = struct.unpack_from(_FIN_FMT, body, pos)
        (
            liutong_guben, province, industry, updated_date, ipo_date,
            zong_guben, guojia_gu, faqiren_faren_gu, faren_gu, b_gu, h_gu, zhigong_gu,
            zong_zichan, liudong_zichan, guding_zichan, wuxing_zichan,
            gudong_renshu,
            liudong_fuzhai, changqi_fuzhai, ziben_gongjijin, jing_zichan,
            zhuying_shouru, zhuying_lirun, yingshou_zhangkuan, yingye_lirun,
            touzi_shouyu, jingying_xianjinliu, zong_xianjinliu,
            cunhuo, lirun_zonghe, shuihou_lirun, jing_lirun, weifen_lirun,
            meigujing_zichan, reserve2,
        ) = fields

        _SCALE = 10000.0  # 财务数据单位：万元/万股

        return FinanceInfo(
            market=Market(market_b),
            code=code_b.decode("utf-8").rstrip("\x00"),
            liutong_guben=liutong_guben * _SCALE,
            zong_guben=zong_guben * _SCALE,
            guojia_gu=guojia_gu * _SCALE,
            faqiren_faren_gu=faqiren_faren_gu * _SCALE,
            faren_gu=faren_gu * _SCALE,
            b_gu=b_gu * _SCALE,
            h_gu=h_gu * _SCALE,
            zhigong_gu=zhigong_gu * _SCALE,
            province=province,
            industry=industry,
            updated_date=updated_date,
            ipo_date=ipo_date,
            gudong_renshu=gudong_renshu,
            zong_zichan=zong_zichan * _SCALE,
            liudong_zichan=liudong_zichan * _SCALE,
            guding_zichan=guding_zichan * _SCALE,
            wuxing_zichan=wuxing_zichan * _SCALE,
            liudong_fuzhai=liudong_fuzhai * _SCALE,
            changqi_fuzhai=changqi_fuzhai * _SCALE,
            ziben_gongjijin=ziben_gongjijin * _SCALE,
            jing_zichan=jing_zichan * _SCALE,
            zhuying_shouru=zhuying_shouru * _SCALE,
            zhuying_lirun=zhuying_lirun * _SCALE,
            yingshou_zhangkuan=yingshou_zhangkuan * _SCALE,
            yingye_lirun=yingye_lirun * _SCALE,
            touzi_shouyu=touzi_shouyu * _SCALE,
            jingying_xianjinliu=jingying_xianjinliu * _SCALE,
            zong_xianjinliu=zong_xianjinliu * _SCALE,
            cunhuo=cunhuo * _SCALE,
            lirun_zonghe=lirun_zonghe * _SCALE,
            shuihou_lirun=shuihou_lirun * _SCALE,
            jing_lirun=jing_lirun * _SCALE,
            weifen_lirun=weifen_lirun * _SCALE,
            meigujing_zichan=meigujing_zichan,
            reserve2=reserve2,
            _raw=body,
        )
