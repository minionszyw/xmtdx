"""异步 transport 回归测试。"""

from __future__ import annotations

import asyncio
import struct
import time

from xmtdx import AsyncTdxClient, Market
from xmtdx.commands.security_count import GetSecurityCountCmd
from xmtdx.commands.setup import SETUP_COMMANDS
from xmtdx.exceptions import TdxConnectionError


def _pack_frame(body: bytes) -> bytes:
    return struct.pack("<IIIHH", 0, 0, 0, len(body), len(body)) + body


def test_async_client_serializes_concurrent_calls() -> None:
    request_len = len(GetSecurityCountCmd(Market.SH).build_request())

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            for setup_cmd in SETUP_COMMANDS:
                await reader.readexactly(len(setup_cmd))
                writer.write(_pack_frame(b""))
                await writer.drain()

            await reader.readexactly(request_len)
            writer.write(_pack_frame(struct.pack("<H", 5)))
            await writer.drain()

            await reader.readexactly(request_len)
            writer.write(_pack_frame(struct.pack("<H", 6)))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def main() -> None:
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            client = AsyncTdxClient("127.0.0.1", port=port, timeout=0.2)
            await client.connect()
            try:
                sh_count, sz_count = await asyncio.gather(
                    client.get_security_count(Market.SH),
                    client.get_security_count(Market.SZ),
                )
            finally:
                await client.close()
        finally:
            server.close()
            await server.wait_closed()

        assert sh_count == 5
        assert sz_count == 6

    asyncio.run(main())


def test_async_client_auto_reconnect() -> None:
    request_len = len(GetSecurityCountCmd(Market.SH).build_request())
    connection_ids: list[int] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection_ids.append(len(connection_ids) + 1)
        connection_id = connection_ids[-1]
        try:
            for setup_cmd in SETUP_COMMANDS:
                await reader.readexactly(len(setup_cmd))
                writer.write(_pack_frame(b""))
                await writer.drain()

            await reader.readexactly(request_len)
            writer.write(_pack_frame(struct.pack("<H", 10 + connection_id)))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def main() -> None:
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            client = AsyncTdxClient("127.0.0.1", port=port, timeout=0.2)
            first = await client.get_security_count(Market.SH)
            second = await client.get_security_count(Market.SH)
            await client.close()
        finally:
            server.close()
            await server.wait_closed()

        assert first == 11
        assert second == 12
        assert len(connection_ids) == 2

    asyncio.run(main())


def test_async_client_request_timeout() -> None:
    request_len = len(GetSecurityCountCmd(Market.SH).build_request())

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            for setup_cmd in SETUP_COMMANDS:
                await reader.readexactly(len(setup_cmd))
                writer.write(_pack_frame(b""))
                await writer.drain()

            await reader.readexactly(request_len)
            await asyncio.sleep(1.0)
        finally:
            writer.close()
            await writer.wait_closed()

    async def main() -> None:
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            client = AsyncTdxClient("127.0.0.1", port=port, timeout=0.05)
            await client.connect()
            t0 = time.monotonic()
            try:
                await client.get_security_count(Market.SH)
            except TdxConnectionError as exc:
                elapsed = time.monotonic() - t0
                assert "超时" in str(exc) or "timed out" in str(exc)
                assert elapsed < 0.3
            else:  # pragma: no cover - 防御性断言
                raise AssertionError("expected timeout")
            finally:
                await client.close()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(main())
