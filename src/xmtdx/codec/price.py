"""变长有符号整数编解码（通达信 TCP 价格编码）。

协议规则：
  - 首字节：bit7=继续标记，bit6=符号（1=负），bit5~0=低6位数据
  - 后续字节：bit7=继续标记，bit6~0=7位数据
  - 所有数据位低位在前（小端 bit 顺序）

典型用途：价格差分、成交量差分、买卖档位数量。
"""

from ..exceptions import TdxDecodeError


def get_price(data: bytes | bytearray, pos: int) -> tuple[int, int]:
    """解码一个变长有符号整数。

    Returns:
        (value, new_pos)
    """
    bit_shift = 6
    start = pos
    try:
        b = data[pos]
        value = b & 0x3F
        negative = bool(b & 0x40)

        if b & 0x80:
            while True:
                pos += 1
                b = data[pos]
                value |= (b & 0x7F) << bit_shift
                bit_shift += 7
                if not (b & 0x80):
                    break
    except IndexError as e:
        raise TdxDecodeError(f"price varint 截断: offset={start}") from e

    pos += 1
    return (-value if negative else value), pos


def put_price(value: int) -> bytes:
    """将整数编码为变长格式（用于构造请求包）。"""
    negative = value < 0
    value = abs(value)

    # 首字节：低6位数据 + 符号位
    first = value & 0x3F
    value >>= 6
    if negative:
        first |= 0x40
    if value:
        first |= 0x80

    result = bytearray([first])

    while value:
        b = value & 0x7F
        value >>= 7
        if value:
            b |= 0x80
        result.append(b)

    return bytes(result)
