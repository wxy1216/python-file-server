from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    SUCCESS = 0

    # 10000 参数类错误
    INVALID_PARAM = 10001
    PARAM_MISSING = 10002

    # 20000 鉴权认证类错误
    NOT_LOGGED_IN = 20001
    TOKEN_EXPIRED = 20002
    ACCOUNT_DISABLED = 20003
    FORBIDDEN = 20004

    # 30000 业务类错误
    FILE_NOT_FOUND = 30001
    FILE_ALREADY_EXISTS = 30002
    FILE_TOO_LARGE = 30003

    # 40000 组件类错误（预留）
    DATABASE_ERROR = 40001
    SYSTEM_COMMAND_ERROR = 40002
    EXTERNAL_API_ERROR = 40003

    # 99999 未知异常
    UNKNOWN = 99999


class BizError(Exception):
    def __init__(
        self,
        code: int,
        msg: str,
        data: Any = None,
        http_status_code: int = 200,
    ) -> None:
        self.code = code
        self.msg = msg
        self.data = data
        self.http_status_code = http_status_code
        super().__init__(msg)


class NotLoggedInError(BizError):
    def __init__(self, msg: str = "user not logged in", data: Any = None) -> None:
        super().__init__(ErrorCode.NOT_LOGGED_IN, msg, data, http_status_code=401)


class AccountDisabledError(BizError):
    def __init__(self, msg: str = "account status abnormal", data: Any = None) -> None:
        super().__init__(ErrorCode.ACCOUNT_DISABLED, msg, data, http_status_code=403)


class FileNotFoundBizError(BizError):
    def __init__(self, msg: str = "file not found", data: Any = None) -> None:
        super().__init__(ErrorCode.FILE_NOT_FOUND, msg, data, http_status_code=404)


class FileTooLargeError(BizError):
    def __init__(self, msg: str = "file too large", data: Any = None) -> None:
        super().__init__(ErrorCode.FILE_TOO_LARGE, msg, data, http_status_code=413)


class SvcError(Exception):
    def __init__(self, code: int, msg: str, data: Any = None) -> None:
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(msg)


class DatabaseError(SvcError):
    def __init__(self, msg: str = "database error", data: Any = None) -> None:
        super().__init__(ErrorCode.DATABASE_ERROR, msg, data)


class SystemCommandError(SvcError):
    def __init__(self, msg: str = "system command error", data: Any = None) -> None:
        super().__init__(ErrorCode.SYSTEM_COMMAND_ERROR, msg, data)


class ExternalAPIError(SvcError):
    def __init__(self, msg: str = "external api error", data: Any = None) -> None:
        super().__init__(ErrorCode.EXTERNAL_API_ERROR, msg, data)
