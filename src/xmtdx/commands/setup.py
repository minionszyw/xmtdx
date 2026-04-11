"""握手命令原始字节（从 pytdx/parser/setup_commands.py 移植，已在真实服务器验证）。

连接建立后必须按序发送三条握手命令，每条均需读取并丢弃响应。
"""

from typing import Final

# 从 pytdx 源码原文复制，去除空格
SETUP_CMD1: Final[bytes] = bytes.fromhex("0c0218930001030003000d0001")
SETUP_CMD2: Final[bytes] = bytes.fromhex("0c0218940001030003000d0002")
SETUP_CMD3: Final[bytes] = bytes.fromhex(
    "0c031899000120002000db0f"
    "d5d0c9ccd6a4a8af0000008f"
    "c22540130000d500c9ccbdf0"
    "d7ea00000002"
)

SETUP_COMMANDS: Final[tuple[bytes, ...]] = (SETUP_CMD1, SETUP_CMD2, SETUP_CMD3)
