"""HTTP 请求周期内的操作人上下文（供访问日志、业务日志、金额审计日志使用）。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

from app.services.user_service import decode_access_token

_operator_label: ContextVar[str] = ContextVar("_operator_label", default="-")


def _label_from_authorization(authorization: Optional[str]) -> str:
    if not authorization or not str(authorization).startswith("Bearer "):
        return "-"
    raw = str(authorization).split(" ", 1)[1].strip()
    payload = decode_access_token(raw)
    if not payload:
        return "-"
    uid = payload.get("uid") or payload.get("sub")
    role = payload.get("role")
    username = payload.get("username")
    if uid is not None and role is not None:
        return f"uid={uid} role={role}"
    if uid is not None:
        return f"uid={uid}"
    if username:
        return str(username)
    return "-"


def bind_operator_context(authorization_header: Optional[str]) -> Token[str]:
    """解析 Authorization，绑定当前协程上下文中的操作人标签；返回的 token 须在 finally 中 reset。"""
    return _operator_label.set(_label_from_authorization(authorization_header))


def reset_operator_context(token: Token[str]) -> None:
    _operator_label.reset(token)


def get_request_operator_label() -> str:
    return _operator_label.get()
