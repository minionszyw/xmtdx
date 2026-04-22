"""同步 transport 回归测试。"""

from unittest.mock import patch

from xmtdx.exceptions import TdxConnectionError
from xmtdx.transport.sync import TdxConnection


class _FakeSocket:
    def __init__(self) -> None:
        self.timeout: float | None = None
        self.connected_to: tuple[str, int] | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, address: tuple[str, int]) -> None:
        self.connected_to = address

    def close(self) -> None:
        self.closed = True


def test_sync_connection_closes_socket_when_setup_fails() -> None:
    sock = _FakeSocket()
    conn = TdxConnection("127.0.0.1", port=7709, timeout=0.2)

    with patch("xmtdx.transport.sync.socket.socket", return_value=sock), patch.object(
        TdxConnection,
        "_send_setup",
        side_effect=TdxConnectionError("setup failed"),
    ):
        try:
            conn.connect()
        except TdxConnectionError as exc:
            assert "setup failed" in str(exc)
        else:  # pragma: no cover - 防御性断言
            raise AssertionError("expected setup failure")

    assert sock.timeout == 0.2
    assert sock.connected_to == ("127.0.0.1", 7709)
    assert sock.closed is True
    assert conn._sock is None
