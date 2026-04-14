"""获取实时五档行情命令（最多 80 只/次）。

所有未知字段（unknown_N）保留原始解析值，供逆向分析。
"""

import struct

from .._binary import unpack_from
from ..codec.price import get_price
from ..codec.volume import get_volume
from ..exceptions import TdxDecodeError
from ..models.enums import Market
from ..models.quote import SecurityQuote
from .base import BaseCommand


def _format_server_time(raw: int) -> str:
    """将 reversed_bytes0 整数转换为 HH:MM:SS.mmm 字符串。

    方法来自 pytdx issue #187。raw 为 14999212 → "14:59:57.163"
    """
    s = str(raw)
    if len(s) < 6:
        return s
    # 最后6位：前两位=秒，后四位=毫秒的某种编码
    time_part = s[:-6] + ":"
    last6 = int(s[-6:])
    if int(s[-6:-4]) < 60:
        time_part += s[-6:-4] + ":"
        time_part += f"{last6 % 10000 * 60 / 10000.0:06.3f}"
    else:
        mins = last6 * 60 // 1000000
        secs = (last6 * 60 % 1000000) * 60 / 1000000.0
        time_part += f"{mins:02d}:{secs:06.3f}"
    return time_part


class GetSecurityQuotesCmd(BaseCommand[list[SecurityQuote]]):
    """批量获取实时行情（最多 80 只）。

    Args:
        stocks: [(market, code), ...] 列表
    """

    def __init__(self, stocks: list[tuple[Market, str]]) -> None:
        if not stocks:
            raise ValueError("stocks 不能为空")
        if len(stocks) > 80:
            raise ValueError("单次最多查询 80 只股票")
        self.stocks = stocks

    def build_request(self) -> bytes:
        n = len(self.stocks)
        payload_len = n * 7 + 12
        header = struct.pack(
            "<HIHHIIHH",
            0x010C,
            0x02006320,
            payload_len,
            payload_len,
            0x0005053E,
            0,
            0,
            n,
        )
        body = bytearray(header)
        for market, code in self.stocks:
            body.extend(struct.pack("<B6s", int(market), code.encode("utf-8")))
        return bytes(body)

    def parse_response(self, body: bytes) -> list[SecurityQuote]:
        pos = 0
        # pytdx 跳过前2字节（b1 cb 魔数）
        pos += 2
        (num,) = unpack_from("<H", body, pos, "security_quotes header")
        pos += 2

        results: list[SecurityQuote] = []

        for _ in range(num):
            record_start = pos

            market_b, code_b, active1 = unpack_from(
                "<B6sH",
                body,
                pos,
                "security_quotes record header",
            )
            pos += 9

            price_raw, pos = get_price(body, pos)
            last_close_diff, pos = get_price(body, pos)
            open_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            # unknown_0: 服务器时间戳原始整数（get_price 解码）
            unknown_0, pos = get_price(body, pos)
            # unknown_1: 通常等于 -price_raw（pytdx 注释推测）
            unknown_1, pos = get_price(body, pos)

            vol, pos = get_price(body, pos)
            cur_vol, pos = get_price(body, pos)

            amount, _ = get_volume(body, pos)
            pos += 4

            s_vol, pos = get_price(body, pos)
            b_vol, pos = get_price(body, pos)

            unknown_2, pos = get_price(body, pos)
            unknown_3, pos = get_price(body, pos)

            # 五档买盘
            bid1_d, pos = get_price(body, pos)
            ask1_d, pos = get_price(body, pos)
            bv1, pos = get_price(body, pos)
            av1, pos = get_price(body, pos)

            bid2_d, pos = get_price(body, pos)
            ask2_d, pos = get_price(body, pos)
            bv2, pos = get_price(body, pos)
            av2, pos = get_price(body, pos)

            bid3_d, pos = get_price(body, pos)
            ask3_d, pos = get_price(body, pos)
            bv3, pos = get_price(body, pos)
            av3, pos = get_price(body, pos)

            bid4_d, pos = get_price(body, pos)
            ask4_d, pos = get_price(body, pos)
            bv4, pos = get_price(body, pos)
            av4, pos = get_price(body, pos)

            bid5_d, pos = get_price(body, pos)
            ask5_d, pos = get_price(body, pos)
            bv5, pos = get_price(body, pos)
            av5, pos = get_price(body, pos)

            # 尾部：2字节 H + 4个 get_price + 2字节 h + 2字节 H
            (unknown_4,) = unpack_from("<H", body, pos, "security_quotes tail flag")
            pos += 2
            unknown_5, pos = get_price(body, pos)
            unknown_6, pos = get_price(body, pos)
            unknown_7, pos = get_price(body, pos)
            unknown_8, pos = get_price(body, pos)
            rise_speed_raw, active2 = unpack_from(
                "<hH",
                body,
                pos,
                "security_quotes tail",
            )
            pos += 4

            p = price_raw / 100.0
            try:
                market = Market(market_b)
            except ValueError as e:
                raise TdxDecodeError(f"security_quotes 非法 market 值: {market_b}") from e

            results.append(
                SecurityQuote(
                    market=market,
                    code=code_b.decode("utf-8").rstrip("\x00"),
                    price=p,
                    pre_close=(price_raw + last_close_diff) / 100.0,
                    open=(price_raw + open_diff) / 100.0,
                    high=(price_raw + high_diff) / 100.0,
                    low=(price_raw + low_diff) / 100.0,
                    vol=float(vol),
                    cur_vol=float(cur_vol),
                    amount=amount,
                    s_vol=float(s_vol),
                    b_vol=float(b_vol),
                    active1=active1,
                    active2=active2,
                    bid1=(price_raw + bid1_d) / 100.0,
                    bid_vol1=float(bv1),
                    bid2=(price_raw + bid2_d) / 100.0,
                    bid_vol2=float(bv2),
                    bid3=(price_raw + bid3_d) / 100.0,
                    bid_vol3=float(bv3),
                    bid4=(price_raw + bid4_d) / 100.0,
                    bid_vol4=float(bv4),
                    bid5=(price_raw + bid5_d) / 100.0,
                    bid_vol5=float(bv5),
                    ask1=(price_raw + ask1_d) / 100.0,
                    ask_vol1=float(av1),
                    ask2=(price_raw + ask2_d) / 100.0,
                    ask_vol2=float(av2),
                    ask3=(price_raw + ask3_d) / 100.0,
                    ask_vol3=float(av3),
                    ask4=(price_raw + ask4_d) / 100.0,
                    ask_vol4=float(av4),
                    ask5=(price_raw + ask5_d) / 100.0,
                    ask_vol5=float(av5),
                    rise_speed=rise_speed_raw / 100.0,
                    limit_up=(price_raw + unknown_2) / 100.0,
                    limit_down=(price_raw + unknown_3) / 100.0,
                    unknown_2=unknown_2,
                    unknown_3=unknown_3,
                    unknown_5=unknown_5,
                    unknown_6=unknown_6,
                    unknown_7=unknown_7,
                    unknown_8=unknown_8,
                    server_time=_format_server_time(unknown_0),
                    _raw=body[record_start:pos],
                )
            )

        return results
