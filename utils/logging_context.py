"""
日志上下文工具 - 为向后兼容而保留
建议直接使用 utils.logger_loguru 中的 log_with_ctx 函数
"""

from typing import Optional
from utils.logger_loguru import log_with_ctx, format_conn_key

# 重新导出函数以保持向后兼容
__all__ = ["log_with_ctx", "format_conn_key"]
