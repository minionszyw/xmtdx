"""同步 TCP 连接（基于 socket）。"""

import socket
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar

from ..codec.frame import HEADER_SIZE, decompress_body, parse_header
from ..commands.setup import SETUP_COMMANDS
from ..exceptions import TdxConnectionError

if TYPE_CHECKING:
    from ..commands.base import BaseCommand

T = TypeVar("T")

_DEFAULT_HOST = "180.153.18.170"
_DEFAULT_PORT = 7709
_DEFAULT_TIMEOUT = 15.0


class TdxConnection:
    """同步通达信 TCP 连接。

    使用示例::

        with TdxConnection("180.153.18.170") as conn:
            result = conn.execute(SomeCommand(...))
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        """建立 TCP 连接并完成握手（发送3条 setup 命令）。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._sock = sock
        self._send_setup()

    def close(self) -> None:
        """关闭连接。"""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        if self._sock is None:
            raise TdxConnectionError("未连接，请先调用 connect()")
        request = cmd.build_request()
        try:
            self._sock.sendall(request)
            header_buf = self._recv_exact(HEADER_SIZE)
            header = parse_header(header_buf)
            raw_body = self._recv_exact(header.zipsize)
        except OSError as e:
            raise TdxConnectionError(f"通信错误: {e}") from e
        body = decompress_body(header, raw_body)
        return cmd.parse_response(body)

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "TdxConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _send_setup(self) -> None:
        """按序发送三条握手命令并丢弃响应。"""
        assert self._sock is not None
        for cmd_bytes in SETUP_COMMANDS:
            self._sock.sendall(cmd_bytes)
            # 读取并丢弃握手响应
            try:
                hdr_buf = self._recv_exact(HEADER_SIZE)
                hdr = parse_header(hdr_buf)
                if hdr.zipsize > 0:
                    self._recv_exact(hdr.zipsize)
            except OSError:
                # 部分服务器的握手无响应，忽略错误
                pass

    def _recv_exact(self, n: int) -> bytes:
        """循环 recv 直到读满 n 字节。"""
        assert self._sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise TdxConnectionError("连接被服务器关闭")
            buf.extend(chunk)
        return bytes(buf)
