"""异步 TCP 连接（基于 asyncio）。"""

import asyncio
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar

from ..codec.frame import HEADER_SIZE, decompress_body, parse_header
from ..commands.setup import SETUP_COMMANDS
from ..exceptions import TdxConnectionError, TdxError
from .capture import CapturedResponse

if TYPE_CHECKING:
    from ..commands.base import BaseCommand

T = TypeVar("T")

_DEFAULT_HOST = "180.153.18.170"
_DEFAULT_PORT = 7709
_DEFAULT_TIMEOUT = 15.0


async def ping_host_async(
    host: str,
    port: int = _DEFAULT_PORT,
    timeout: float = 5.0,
) -> float | None:
    """异步验证完整握手和证券数量查询，返回端到端延迟。"""
    from ..commands.security_count import GetSecurityCountCmd
    from ..models.enums import Market

    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with AsyncTdxConnection(host, port, timeout) as conn:
            if await conn.execute(GetSecurityCountCmd(Market.SH)) <= 0:
                return None
    except (OSError, TdxError):
        return None
    return loop.time() - started


async def ping_all_async(
    hosts: list[str],
    port: int = _DEFAULT_PORT,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发验证异步行情主机，返回按端到端延迟排序的结果。"""
    latencies = await asyncio.gather(
        *(ping_host_async(host, port, timeout) for host in hosts)
    )
    results = [
        (host, latency)
        for host, latency in zip(hosts, latencies, strict=True)
        if latency is not None
    ]
    return sorted(results, key=lambda item: item[1])


class AsyncTdxConnection:
    """异步通达信 TCP 连接（asyncio）。

    使用示例::

        async with AsyncTdxConnection("180.153.18.170") as conn:
            result = await conn.execute(SomeCommand(...))
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
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        # 单连接不支持请求复用；所有 IO 在连接内串行执行。
        self._io_lock = asyncio.Lock()

    async def connect(self) -> None:
        """建立 TCP 连接并完成握手。"""
        async with self._io_lock:
            if self._writer is not None and not self._writer.is_closing():
                return
            await self._connect_unlocked()

    async def close(self) -> None:
        """关闭连接。"""
        async with self._io_lock:
            await self._close_unlocked()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令（异步版本）。

        同一连接上的并发调用会在此处串行化，避免 StreamReader 并发读取冲突。
        """
        return (await self.capture(cmd)).result

    async def capture(self, cmd: "BaseCommand[T]") -> CapturedResponse[T]:
        """执行命令并保留请求、帧头、原始响应及解压结果。"""
        async with self._io_lock:
            if self._writer is None or self._reader is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
            try:
                self._writer.write(request)
                await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
                header_buf = await self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = await self._recv_exact(header.zipsize)
            except asyncio.TimeoutError as e:
                await self._close_unlocked()
                raise TdxConnectionError(f"通信超时: {self.timeout}s") from e
            except (OSError, asyncio.IncompleteReadError) as e:
                await self._close_unlocked()
                raise TdxConnectionError(f"通信错误: {e}") from e

            try:
                body = decompress_body(header, raw_body)
                result = cmd.parse_response(body)
            except TdxError:
                await self._close_unlocked()
                raise
            if not cmd.reusable_connection:
                await self._close_unlocked()
            return CapturedResponse(request, header, raw_body, body, result)

    async def _connect_unlocked(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._reader = reader
        self._writer = writer
        try:
            await self._send_setup()
        except TdxError:
            await self._close_unlocked()
            raise
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as error:
            await self._close_unlocked()
            raise TdxConnectionError(
                f"握手失败 {self.host}:{self.port}: {error}"
            ) from error

    async def _close_unlocked(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._reader = None
            self._writer = None

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "AsyncTdxConnection":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    async def _send_setup(self) -> None:
        """按序发送三条握手命令并丢弃响应。"""
        assert self._writer is not None
        assert self._reader is not None
        for cmd_bytes in SETUP_COMMANDS:
            self._writer.write(cmd_bytes)
            await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
            hdr_buf = await self._recv_exact(HEADER_SIZE)
            hdr = parse_header(hdr_buf)
            raw_body = await self._recv_exact(hdr.zipsize)
            decompress_body(hdr, raw_body)

    async def _recv_exact(self, n: int) -> bytes:
        """读满 n 字节。"""
        assert self._reader is not None
        data = await asyncio.wait_for(
            self._reader.readexactly(n),
            timeout=self.timeout,
        )
        return data
