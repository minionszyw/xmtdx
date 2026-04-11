"""获取市场股票/证券总数命令。"""

import struct

from .._binary import unpack_from
from ..models.enums import Market
from .base import BaseCommand


class GetSecurityCountCmd(BaseCommand[int]):
    """返回指定市场的证券总数。

    心跳命令也可复用此命令（pytdx 用随机 market 发心跳）。
    """

    def __init__(self, market: Market) -> None:
        self.market = market

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c0c186c000108000800 4e04".replace(" ", ""))
        return header + struct.pack("<H", int(self.market)) + b"\x75\xc7\x33\x01"

    def parse_response(self, body: bytes) -> int:
        (count,) = unpack_from("<H", body, 0, "security_count")
        return int(count)
