"""命令基类：只含请求构造与响应解析，不含任何 IO。

transport 层负责：发送请求、接收帧头、接收 body、解压，
然后调用 command.parse_response(body) 得到结果。
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class BaseCommand(ABC, Generic[T]):
    """所有行情命令的基类。

    子类实现：
      build_request()  → 返回要发送的原始字节
      parse_response() → 从解压后的 body 返回强类型结果
    """

    @abstractmethod
    def build_request(self) -> bytes:
        """构造请求包（含完整帧头）。"""
        ...

    @abstractmethod
    def parse_response(self, body: bytes) -> T:
        """解析解压后的响应 body，返回强类型结果。"""
        ...
