"""金额相关变更的独立审计日志（logger 名 app.finance_audit，见 logging_config 中的 handler 配置）。"""

from __future__ import annotations

import logging


def log_finance_event(msg: str, *args) -> None:
    """写入金额/税率/运费/报价等变更审计；操作人由 logging Filter 从请求上下文注入格式字段。"""
    logging.getLogger("app.finance_audit").info(msg, *args)
