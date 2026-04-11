"""坏包与解码异常回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xmtdx.codec.frame import FrameHeader, decompress_body
from xmtdx.commands.company_info import GetCompanyInfoCategoryCmd
from xmtdx.commands.security_count import GetSecurityCountCmd
from xmtdx.commands.xdxr_info import GetXdxrInfoCmd
from xmtdx.exceptions import TdxDecodeError
from xmtdx.models.enums import Market

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_hex(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / f"{name}.hex").read_text().strip())


def test_security_count_truncated_raises_tdxdecodeerror() -> None:
    with pytest.raises(TdxDecodeError):
        GetSecurityCountCmd(Market.SH).parse_response(b"")


def test_company_info_category_truncated_raises_tdxdecodeerror() -> None:
    body = _load_hex("company_info_category")
    cmd = GetCompanyInfoCategoryCmd(Market.SH, "600000")

    with pytest.raises(TdxDecodeError):
        cmd.parse_response(body[:-10])


def test_xdxr_info_truncated_raises_tdxdecodeerror() -> None:
    body = _load_hex("xdxr_info")
    cmd = GetXdxrInfoCmd(Market.SH, "600000")

    with pytest.raises(TdxDecodeError):
        cmd.parse_response(body[:-10])


def test_frame_bad_zlib_raises_tdxdecodeerror() -> None:
    with pytest.raises(TdxDecodeError):
        decompress_body(FrameHeader(0, 0, 0, 4, 8), b"xxxx")


def test_frame_unzipsize_mismatch_raises_tdxdecodeerror() -> None:
    with pytest.raises(TdxDecodeError):
        decompress_body(FrameHeader(0, 0, 0, 3, 4), b"abc")
