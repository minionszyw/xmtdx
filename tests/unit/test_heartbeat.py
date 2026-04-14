"""心跳机制单元测试。"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from xmtdx import AsyncTdxClient, Market


@pytest.mark.asyncio
async def test_heartbeat_sends_periodically():
    # 模拟连接和执行
    with patch("xmtdx.client.AsyncTdxConnection") as mock_conn_cls:
        mock_conn = mock_conn_cls.return_value
        mock_conn.connect = AsyncMock()
        mock_conn.close = AsyncMock()
        
        # 记录调用次数
        call_count = 0
        async def mock_execute(cmd):
            nonlocal call_count
            call_count += 1
            return 5 # 模拟 get_security_count 返回值

        mock_conn.execute.side_effect = mock_execute

        # 设置非常短的心跳间隔以便测试
        client = AsyncTdxClient("127.0.0.1", heartbeat_interval=0.1)
        await client.connect()
        
        # 等待几次心跳周期
        await asyncio.sleep(0.35)
        
        await client.close()
        
        # 0.35s 应该触发约 3 次心跳 (0.1, 0.2, 0.3)
        assert call_count >= 3


@pytest.mark.asyncio
async def test_heartbeat_stops_on_close():
    with patch("xmtdx.client.AsyncTdxConnection") as mock_conn_cls:
        mock_conn = mock_conn_cls.return_value
        mock_conn.connect = AsyncMock()
        mock_conn.close = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=5)
        
        client = AsyncTdxClient("127.0.0.1", heartbeat_interval=0.01)
        await client.connect()
        assert client._heartbeat_task is not None
        
        task = client._heartbeat_task
        await client.close()
        
        assert client._heartbeat_task is None
        assert task.done() or task.cancelled()


if __name__ == "__main__":
    # 手动跑一下
    async def run():
        await test_heartbeat_sends_periodically()
        await test_heartbeat_stops_on_close()
        print("Heartbeat tests passed!")
    
    asyncio.run(run())
