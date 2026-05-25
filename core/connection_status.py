"""
连接状态管理 - 独立模块

职责：维护所有 PDDChannel 实例的连接状态。
从 Channel/pinduoduo/pdd_channel.py 中提取出来，
明确其跨实例共享状态的职责边界。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional


class ConnectionState(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ConnectionStatus:
    """连接状态信息"""
    shop_id: str
    user_id: str
    username: str
    state: ConnectionState
    connect_time: Optional[datetime] = None
    error_count: int = 0
    reconnect_count: int = 0
    last_error: Optional[str] = None
    last_connect_time: Optional[datetime] = None


class ConnectionStatusManager:
    """
    连接状态管理器 - 线程安全

    职责边界：
    - 仅负责存储和查询连接状态
    - 不负责创建/销毁连接
    - 不持有任何 PDDChannel 实例引用
    - 线程安全（使用 RLock）

    单例管理：通过 DI 容器注册为单例（推荐方式）。
    """

    def __init__(self):
        # 仅在首次初始化时设置，避免单例模式下重复初始化
        if not hasattr(self, '_initialized') or not self._initialized:
            self._connections: Dict[str, ConnectionStatus] = {}
            self._lock = RLock()
            self._initialized = True

    def update_status(
        self,
        shop_id: str,
        user_id: str,
        username: str,
        state: ConnectionState,
        error: str = None
    ) -> None:
        """更新连接状态"""
        connection_key = f"{shop_id}_{user_id}"
        with self._lock:
            if connection_key not in self._connections:
                self._connections[connection_key] = ConnectionStatus(
                    shop_id=shop_id,
                    user_id=user_id,
                    username=username,
                    state=state
                )

            status = self._connections[connection_key]
            status.state = state

            if state == ConnectionState.CONNECTED:
                status.connect_time = datetime.now()
                status.last_connect_time = datetime.now()
                status.last_error = None
            elif state == ConnectionState.CONNECTING:
                status.connect_time = None
            elif state == ConnectionState.ERROR and error:
                status.error_count += 1
                status.last_error = error
            elif state == ConnectionState.RECONNECTING:
                status.reconnect_count += 1

    def get_all_status(self) -> List[ConnectionStatus]:
        """获取所有连接状态"""
        with self._lock:
            return list(self._connections.values())

    def get_connected_count(self) -> int:
        """获取当前连接数"""
        with self._lock:
            return sum(
                1 for status in self._connections.values()
                if status.state == ConnectionState.CONNECTED
            )

    def get_status(self, shop_id: str, user_id: str) -> Optional[ConnectionStatus]:
        """获取指定连接状态"""
        connection_key = f"{shop_id}_{user_id}"
        with self._lock:
            return self._connections.get(connection_key)

    def clear_connection(self, shop_id: str, user_id: str) -> None:
        """清除连接记录"""
        connection_key = f"{shop_id}_{user_id}"
        with self._lock:
            self._connections.pop(connection_key, None)

    def clear_all(self) -> None:
        """清空所有连接状态（应用关闭时调用）"""
        with self._lock:
            self._connections.clear()
