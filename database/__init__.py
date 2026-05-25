"""
数据库模块初始化文件

此模块导出数据库管理器代理，确保整个应用程序使用 DI 容器中的同一实例。
通过 _LazyDBProxy 提供向后兼容，底层转发到 DI 容器。
"""

from .db_manager import DatabaseManager, get_db_manager
from core.service_providers import _create_proxy

# 创建 DI 代理：现有代码 `from database import db_manager` 无需修改
db_manager = _create_proxy(DatabaseManager)

__all__ = ["get_db_manager", "db_manager", "DatabaseManager"]
