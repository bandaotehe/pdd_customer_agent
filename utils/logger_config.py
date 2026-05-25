#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
简化的日志配置管理模块 - 基于loguru的轻量级配置
"""

import os
import sys
from typing import Dict, Any
from loguru import logger

class SimpleLoggerConfig:
    """简化的日志配置管理器"""

    def __init__(self):
        self.environment = self._detect_environment()
        self.log_level = self._get_log_level()

    def _detect_environment(self) -> str:
        """检测运行环境"""
        env = os.environ.get("ENVIRONMENT", "").lower()
        if env in ["development", "testing", "production"]:
            return env

        # 通过环境变量推断
        if os.environ.get("DEBUG") == "1":
            return "development"
        elif os.environ.get("TESTING") == "1":
            return "testing"
        else:
            return "production"

    def _get_log_level(self) -> str:
        """获取日志级别"""
        # 优先使用LOG_LEVEL环境变量
        level = os.environ.get("LOG_LEVEL", "").upper()
        if level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            return level

        # 根据环境设置默认级别
        return {
            "development": "DEBUG",
            "testing": "INFO",
            "production": "INFO"
        }.get(self.environment, "INFO")

    def is_business_logging_enabled(self) -> bool:
        """检查是否启用业务日志"""
        return os.environ.get("BUSINESS_LOGGING", "true").lower() == "true"

    def is_ui_logging_enabled(self) -> bool:
        """检查是否启用UI日志"""
        return os.environ.get("UI_LOGGING", "true").lower() == "true"

    def get_log_retention_days(self) -> int:
        """获取日志保留天数"""
        return int(os.environ.get("LOG_RETENTION_DAYS", "7"))

    def get_log_rotation_size(self) -> str:
        """获取日志轮转大小"""
        return os.environ.get("LOG_ROTATION_SIZE", "10 MB")

    def configure_for_environment(self):
        """根据环境配置loguru"""
        # 移除现有处理器
        logger.remove()

        # 根据环境配置不同日志
        if self.environment == "development":
            # 开发环境：详细日志，同时输出到控制台和文件
            logger.add(
                sys.stderr,
                format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                level=self.log_level,
                colorize=True
            )
            logger.add(
                "logs/dev.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                level="DEBUG",
                rotation="5 MB",
                retention="3 days"
            )
        elif self.environment == "testing":
            # 测试环境：仅文件日志
            logger.add(
                "logs/test.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                level=self.log_level,
                rotation="10 MB",
                retention="1 day"
            )
        else:
            # 生产环境：优化的日志配置
            logger.add(
                sys.stderr,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
                level=self.log_level,
                filter=lambda record: record["level"].name in ["WARNING", "ERROR", "CRITICAL"]
            )
            logger.add(
                "logs/app.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                level=self.log_level,
                rotation=self.get_log_rotation_size(),
                retention=f"{self.get_log_retention_days()} days",
                compression="zip"
            )

# 全局配置实例
_global_config = None

def get_logger_config() -> SimpleLoggerConfig:
    """获取全局日志配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = SimpleLoggerConfig()
    return _global_config

def get_log_level() -> str:
    """获取当前日志级别"""
    return get_logger_config().log_level

def is_business_logging_enabled() -> bool:
    """检查是否启用业务日志"""
    return get_logger_config().is_business_logging_enabled()

def get_environment() -> str:
    """获取当前环境"""
    return get_logger_config().environment