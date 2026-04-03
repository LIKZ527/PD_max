import logging
import logging.handlers
import os
import sys
from pathlib import Path

# 避免用「root 是否已有 handlers」判断：其它库或运行环境可能先挂过 handler（甚至 NullHandler），
# 会导致此处直接 return，应用侧 StreamHandler 从未添加，表现为「没有任何业务日志」。
_handlers_installed = False


def _parse_log_level(value: str) -> int:
    level_name = (value or "INFO").upper().strip()
    return getattr(logging, level_name, logging.INFO)


def setup_logging() -> None:
    """初始化项目日志：handlers 只装一次；LOG_LEVEL 每次生效（便于 reload 后读 .env）。"""
    global _handlers_installed
    root_logger = logging.getLogger()
    level = _parse_log_level(os.getenv("LOG_LEVEL", "INFO"))
    root_logger.setLevel(level)

    if _handlers_installed:
        return

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _handlers_installed = True
