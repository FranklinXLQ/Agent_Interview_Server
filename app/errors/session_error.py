"""会话占用或存储容量不足的业务异常。"""

from typing import Literal


class SessionError(Exception):
    """携带可展示提示与业务原因，由路由映射 HTTP 状态码。"""

    def __init__(self, reason: Literal["busy", "capacity"], message: str) -> None:
        """记录错误原因，不让存储层依赖 HTTP。"""
        super().__init__(message)
        self.reason = reason
