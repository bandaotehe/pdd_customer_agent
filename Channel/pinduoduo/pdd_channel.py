"""
拼多多WebSocket客户端
此模块提供与拼多多商家后台的WebSocket通信功能，用于接收和发送客服消息。
支持多店铺管理、消息队列处理和自动重连机制。

代码已拆分为多个模块：
- core/pdd_config.py: 配置类
- core/pdd_connection.py: 连接管理
- core/pdd_message_handler.py: 消息处理
- core/pdd_lifecycle.py: 生命周期管理
- core/pdd_status.py: 状态查询
- core/pdd_utils.py: 全局便捷函数
"""
from utils.logger_loguru import get_logger
from bridge.context import Context, ContextType, ChannelType
from Channel.pinduoduo.pdd_message import PDDChatMessage
from Channel.channel import Channel
from Channel.pinduoduo.utils.API.get_token import GetToken
from database import db_manager
from utils.resource_manager import WebSocketResourceManager
from core.connection_status import ConnectionStatusManager, ConnectionState, ConnectionStatus
import websockets
import json
from websockets import exceptions as ws_exceptions
import asyncio
import time
from typing import Optional, Dict, List, Set, Any
from dataclasses import dataclass
from config import config

# 导入 Mixin 类
from Channel.pinduoduo.core.pdd_config import ReconnectConfig, HeartbeatConfig
from Channel.pinduoduo.core.pdd_connection import ConnectionMixin
from Channel.pinduoduo.core.pdd_message_handler import MessageHandlerMixin
from Channel.pinduoduo.core.pdd_lifecycle import LifecycleMixin
from Channel.pinduoduo.core.pdd_status import StatusMixin
from Channel.pinduoduo.core.pdd_utils import (
    get_pdd_connection_status,
    get_pdd_connected_count,
    get_pdd_connection_summary,
    get_pdd_heartbeat_status_all,
)


class PDDChannel(ConnectionMixin, MessageHandlerMixin, LifecycleMixin, StatusMixin, Channel):
    """
    拼多多WebSocket客户端 - 支持自动重连和心跳检查

    使用 Mixin 组合模式，代码已拆分为多个功能模块：
    - ConnectionMixin: 连接管理
    - MessageHandlerMixin: 消息处理
    - LifecycleMixin: 生命周期管理
    - StatusMixin: 状态查询

    注意：此类不再强制单例。每个 AutoReplyThread 应创建独立的 PDDChannel 实例
    （各自的事件循环 + WebSocket 连接），但通过 DI 容器共享同一个
    ConnectionStatusManager 来维护全局连接状态。
    """

    # API 版本号
    API_VERSION = "202604301140"

    def __init__(self, max_concurrent_messages: int = 50, status_manager: ConnectionStatusManager = None):
        super().__init__()
        self.channel_name = "pinduoduo"
        self.logger = get_logger("PDDChannel")

        # 从 DI 容器获取 ConnectionStatusManager（所有实例共享同一个）
        if status_manager is None:
            from core.di_container import container
            status_manager = container.get(ConnectionStatusManager)
        self.status_manager = status_manager

        self._stop_event: Optional[asyncio.Event] = None
        self.base_url = "wss://m-ws.pinduoduo.com/"
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.businessHours = config.get("businessHours")

        # WebSocket优化功能
        self.reconnect_config = ReconnectConfig()
        self.heartbeat_config = HeartbeatConfig()
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}

        # 性能优化：并发控制和任务管理
        self.max_concurrent_messages = max_concurrent_messages
        self.message_semaphore = asyncio.Semaphore(max_concurrent_messages)
        self.processing_tasks: Set[asyncio.Task[Any]] = set()

        # 资源管理
        self.resource_manager = WebSocketResourceManager()


# 重新导出全局便捷函数，保持向后兼容
__all__ = [
    'PDDChannel',
    'ReconnectConfig',
    'HeartbeatConfig',
    'get_pdd_connection_status',
    'get_pdd_connected_count',
    'get_pdd_connection_summary',
    'get_pdd_heartbeat_status_all',
]
