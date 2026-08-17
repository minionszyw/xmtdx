"""可复现的单次协议交互捕获。"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from ..codec.frame import FrameHeader

T = TypeVar("T")


@dataclass(frozen=True)
class CapturedResponse(Generic[T]):
    """一次业务请求的原始字节、响应帧和解析结果。"""

    request: bytes
    header: FrameHeader
    raw_body: bytes
    body: bytes
    result: T
