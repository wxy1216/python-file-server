from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    SUCCESS = 0
    NOT_LOGGED_IN = 1001
    TOKEN_EXPIRED = 1002
    ACCOUNT_DISABLED = 1003
    FORBIDDEN = 1004
    FILE_NOT_FOUND = 2001
    FILE_ALREADY_EXISTS = 2002
    FILE_TOO_LARGE = 2003
    INVALID_PARAM = 3001
    PARAM_MISSING = 3002
    UNKNOWN = 5000


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
