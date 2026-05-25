#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基于loguru的日志模块 - 提供全局日志功能，支持结构化日志和异步处理
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union
from pathlib import Path

from loguru import logger

# 可选的PyQt6依赖
try:
    from PyQt6.QtCore import QObject, pyqtSignal
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False
    # 创建占位符类
    class QObject:
        def __init__(self, *args, **kwargs):
            pass
    def pyqtSignal(*args):
        class DummySignal:
            def emit(self, *args, **kwargs):
                pass
            def connect(self, *args, **kwargs):
                pass
            def disconnect(self, *args, **kwargs):
                pass
        return DummySignal()

# 默认配置
DEFAULT_LOG_LEVEL = "info"
DEFAULT_LOG_FILE = "logs/app.log"
MAX_LOG_SIZE = "10 MB"
BACKUP_COUNT = 5

# 确保日志目录存在
os.makedirs(os.path.dirname(DEFAULT_LOG_FILE), exist_ok=True)

# 配置loguru
log_level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).lower()

# 移除默认处理器
logger.remove()

# 检查是否在打包环境中
import sys
is_frozen = getattr(sys, 'frozen', False)

# 添加控制台处理器（仅在开发环境）
if not is_frozen:
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level.upper(),
        colorize=True,
        backtrace=True,
        diagnose=not is_frozen
    )

# 添加文件处理器（自动轮转和压缩）
logger.add(
    DEFAULT_LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level=log_level.upper(),
    rotation=MAX_LOG_SIZE,
    retention=BACKUP_COUNT,
    compression="zip",
    encoding="utf-8",
    backtrace=True,
    diagnose=not is_frozen
)

# 全局logger对象（保持向后兼容）
app_logger = logger

def get_logger(name=None):
    """
    获取logger实例

    Args:
        name: logger名称，如果为None则使用调用模块的名称

    Returns:
        loguru logger实例
    """
    if name is None:
        # 获取调用者的模块名
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')

        # 如果是__main__, 使用文件名
        if name == '__main__':
            filename = frame.f_globals.get('__file__', 'main')
            name = os.path.splitext(os.path.basename(filename))[0]

    # 绑定模块名称到logger
    return logger.bind(module=name)

# 导出全局日志对象和获取logger的函数
__all__ = ["logger", "app_logger", "get_logger", "BusinessLogger", "get_business_logger", "log_with_ctx"]

class BusinessLogger:
    """业务日志记录器，基于loguru实现"""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.logger = logger.bind(business=True, module=module_name)

    def log_message_process(self, user_id: str, message_type: str, processing_time: float, **kwargs) -> None:
        """记录消息处理事件"""
        self.logger.info(
            "消息处理完成",
            extra={
                "event_type": "message_processed",
                "user_id": user_id,
                "message_type": message_type,
                "processing_time_ms": round(processing_time * 1000, 2),
                **kwargs
            }
        )

    def log_agent_response(self, user_id: str, query_length: int, response_length: int, response_time: float, **kwargs) -> None:
        """记录Agent响应事件"""
        self.logger.info(
            "Agent响应生成",
            extra={
                "event_type": "agent_response",
                "user_id": user_id,
                "query_length": query_length,
                "response_length": response_length,
                "response_time_ms": round(response_time * 1000, 2),
                **kwargs
            }
        )

    def log_error(self, error_type: str, error_message: str, user_id: Optional[str] = None, **kwargs) -> None:
        """记录业务错误"""
        self.logger.error(
            "业务错误",
            extra={
                "event_type": "business_error",
                "error_type": error_type,
                "error_message": error_message,
                "user_id": user_id,
                **kwargs
            }
        )

    def log_performance(self, operation: str, duration: float, **kwargs) -> None:
        """记录性能指标"""
        self.logger.info(
            "性能指标",
            extra={
                "event_type": "performance_metric",
                "operation": operation,
                "duration_ms": round(duration * 1000, 2),
                **kwargs
            }
        )

def get_business_logger(module_name: str) -> BusinessLogger:
    """获取业务日志记录器实例"""
    return BusinessLogger(module_name)

# UI集成部分
class UILogHandler(QObject):
    """UI日志处理器，兼容现有LogHandler接口"""

    log_received = pyqtSignal(str, str, object)  # level, message, record

    def __init__(self):
        super().__init__()
        self.handler_id = None
        self._install_loguru_patch()

    def _install_loguru_patch(self):
        """安装loguru拦截器"""
        # 创建一个自定义的处理器来拦截日志
        def ui_sink(message):
            # 解析loguru消息以提取信息
            record = message.record
            level = record["level"].name
            msg = record["message"]
            # 发送信号
            self.log_received.emit(level, msg, record)

        # 安装UI处理器
        self.handler_id = logger.add(ui_sink, level="DEBUG", catch=True)

    def emit(self, record):
        """为了兼容性保留"""
        pass

    def install(self):
        """安装处理器 - 已经在__init__中完成"""
        pass

    def uninstall(self):
        """卸载处理器"""
        if self.handler_id:
            logger.remove(self.handler_id)
            self.handler_id = None

# 上下文日志功能
def format_conn_key(shop_id: Optional[str], user_id: Optional[str]) -> str:
    """格式化连接键"""
    if not shop_id or not user_id:
        return "unknown_unknown"
    return f"{shop_id}_{user_id}"

def log_with_ctx(logger_name: str, msg: str, shop_id: Optional[str] = None,
                 user_id: Optional[str] = None, username: Optional[str] = None,
                 from_uid: Optional[str] = None):
    """带上下文的日志记录"""
    context_parts = []
    if shop_id or user_id:
        context_parts.append(f"key={format_conn_key(shop_id, user_id)}")
    if username:
        context_parts.append(f"user={username}")
    if from_uid:
        context_parts.append(f"from_uid={from_uid}")

    context = f"{' '.join(context_parts)} | " if context_parts else ""
    logger.bind(context=context, logger_name=logger_name).info(f"{context}{msg}")