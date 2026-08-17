"""xmtdx 异常层次"""


class TdxError(Exception):
    """所有 xmtdx 异常的基类"""


class TdxConnectionError(TdxError):
    """TCP 连接失败或超时"""


class TdxDecodeError(TdxError):
    """响应报文解析失败"""


class TdxResponseError(TdxError):
    """响应帧可解析，但内容与请求不匹配或语义无效。"""


class TdxCommandError(TdxError):
    """命令执行失败（服务器返回错误）"""
