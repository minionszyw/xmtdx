"""同步 transport 回归测试。"""

import struct
from unittest.mock import patch

import pytest

from xmtdx import Market
from xmtdx.commands.security_count import GetSecurityCountCmd
from xmtdx.commands.setup import SETUP_COMMANDS
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


class _ScriptedSocket(_FakeSocket):
    def __init__(self, responses: bytes) -> None:
        super().__init__()
        self.responses = bytearray(responses)
        self.requests: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.requests.append(data)

    def recv(self, size: int) -> bytes:
        chunk = bytes(self.responses[:size])
        del self.responses[:size]
        return chunk


def _frame(body: bytes) -> bytes:
    return struct.pack("<IIIHH", 0, 0, 0, len(body), len(body)) + body


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


def test_sync_setup_socket_error_is_normalized() -> None:
    sock = _FakeSocket()
    conn = TdxConnection("127.0.0.1", port=7709, timeout=0.2)

    with patch("xmtdx.transport.sync.socket.socket", return_value=sock), patch.object(
        TdxConnection,
        "_send_setup",
        side_effect=TimeoutError("timed out"),
    ), pytest.raises(TdxConnectionError, match="握手失败"):
        conn.connect()

    assert sock.closed is True


def test_sync_capture_retains_wire_bytes() -> None:
    body = struct.pack("<H", 42)
    sock = _ScriptedSocket(_frame(b"") * len(SETUP_COMMANDS) + _frame(body))
    conn = TdxConnection("127.0.0.1", timeout=0.2)

    with patch("xmtdx.transport.sync.socket.socket", return_value=sock):
        conn.connect()
        command = GetSecurityCountCmd(Market.SH)
        captured = conn.capture(command)
        conn.close()

    assert captured.request == command.build_request()
    assert captured.header.zipsize == len(body)
    assert captured.raw_body == body
    assert captured.body == body
    assert captured.result == 42
    assert sock.requests[:3] == list(SETUP_COMMANDS)
