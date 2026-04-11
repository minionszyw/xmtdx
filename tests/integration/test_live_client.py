"""真实通达信服务器 smoke test。

默认跳过；设置 XMTDX_LIVE=1 后执行。
"""

from __future__ import annotations

import asyncio
import os

import pytest

from xmtdx import AsyncTdxClient, Market, TdxClient

_LIVE_ENABLED = os.getenv("XMTDX_LIVE") == "1"
_LIVE_HOST = os.getenv("XMTDX_HOST", "180.153.18.170")

pytestmark = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason="set XMTDX_LIVE=1 to run live integration tests",
)


def test_sync_live_smoke() -> None:
    with TdxClient(_LIVE_HOST, timeout=5.0) as client:
        assert client.get_security_count(Market.SH) > 0
        assert client.get_security_count(Market.SZ) > 0


def test_async_live_smoke() -> None:
    async def main() -> None:
        async with AsyncTdxClient(_LIVE_HOST, timeout=5.0) as client:
            assert await client.get_security_count(Market.SH) > 0
            assert await client.get_security_count(Market.SZ) > 0

    asyncio.run(main())
