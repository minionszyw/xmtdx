"""同步 TCP 连接（基于 socket）。"""

import socket
import time
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

# 已知可用的通达信行情服务器（按优先级排序）
KNOWN_HOSTS: list[str] = [
    "180.153.18.170",
    "124.71.187.122",
    "180.153.18.171",
    "180.153.18.172",
    "119.147.212.81",
    "115.238.56.198",
    "115.238.90.165",
    "218.75.126.9",
    "47.107.75.159",
    "59.175.238.38",
]


def ping_host(
    host: str,
    port: int = _DEFAULT_PORT,
    timeout: float = 5.0,
) -> float | None:
    """测量连接到指定服务器并完成握手所需的时间（秒）。

    返回延迟（秒），连接失败时返回 None。
    """
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        # 发送第一条握手命令并等待响应作为可用性验证
        sock.sendall(SETUP_COMMANDS[0])
        hdr_buf = _recv_exact_sock(sock, HEADER_SIZE)
        hdr = parse_header(hdr_buf)
        if hdr.zipsize > 0:
            _recv_exact_sock(sock, hdr.zipsize)
        return time.monotonic() - t0
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ping_all(
    hosts: list[str] = KNOWN_HOSTS,
    port: int = _DEFAULT_PORT,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发测量多台服务器延迟，返回按延迟排序的 (host, latency_seconds) 列表。

    不可达的服务器不包含在结果中。
    """
    import concurrent.futures

    results: list[tuple[str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {pool.submit(ping_host, h, port, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            latency = fut.result()
            if latency is not None:
                results.append((host, latency))
    results.sort(key=lambda t: t[1])
    return results


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise TdxConnectionError("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


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
        return _recv_exact_sock(self._sock, n)
