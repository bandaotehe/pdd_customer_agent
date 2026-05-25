"""
WebSocket资源管理器

用于统一管理WebSocket连接和相关资源，提供资源清理和监控功能。
"""
import asyncio
import weakref
from typing import Optional, Set, Any, Dict, List
from utils.logger_loguru import get_logger


class WebSocketResourceManager:
    """
    WebSocket资源管理器

    功能：
    1. 跟踪所有活跃的WebSocket连接
    2. 提供统一的资源清理接口
    3. 监控连接状态和资源使用情况
    """

    def __init__(self):
        self.logger = get_logger("WebSocketResourceManager")
        # 使用弱引用集合避免循环引用
        self._connections: Set[weakref.ref] = set()
        self._connection_names: Dict[int, str] = {}  # 连接名称映射
        self._lock = asyncio.Lock()

    def register_websocket(self, websocket: Any, name: str = None) -> None:
        """
        注册WebSocket连接

        Args:
            websocket: WebSocket连接对象
            name: 连接名称（用于日志和调试）
        """
        def cleanup_callback(ref):
            """弱引用回调，当WebSocket被垃圾回收时清理记录"""
            asyncio.create_task(self._cleanup_reference(ref))

        # 创建弱引用并设置回调
        ref = weakref.ref(websocket, cleanup_callback)
        self._connections.add(ref)

        if name:
            self._connection_names[id(websocket)] = name

        self.logger.debug(f"已注册WebSocket连接: {name or '未命名'}")

    async def cleanup_all(self) -> None:
        """
        清理所有注册的WebSocket连接
        """
        async with self._lock:
            cleaned_count = 0
            errors = []

            # 创建副本避免在迭代时修改集合
            connections_copy = self._connections.copy()

            for ref in connections_copy:
                websocket = ref()
                if websocket is not None:
                    try:
                        # 检查连接是否有close方法
                        if hasattr(websocket, 'close') and not getattr(websocket, 'closed', False):
                            if asyncio.iscoroutinefunction(websocket.close):
                                await websocket.close()
                            else:
                                websocket.close()
                            cleaned_count += 1
                        self._connections.discard(ref)
                    except Exception as e:
                        error_msg = f"清理WebSocket失败: {str(e)}"
                        errors.append(error_msg)
                        self.logger.error(error_msg)
                else:
                    # 引用已失效，直接移除
                    self._connections.discard(ref)

            # 清理连接名称映射
            self._connection_names.clear()

            # 记录清理结果
            if errors:
                self.logger.warning(f"清理完成，成功: {cleaned_count}, 错误: {len(errors)}")
                for error in errors:
                    self.logger.error(f"  - {error}")
            else:
                self.logger.info(f"所有WebSocket连接已清理，共 {cleaned_count} 个连接")

    async def _cleanup_reference(self, ref: weakref.ref) -> None:
        """
        清理弱引用（内部方法）

        Args:
            ref: 要清理的弱引用
        """
        async with self._lock:
            self._connections.discard(ref)
            self.logger.debug("WebSocket连接已被垃圾回收，清理引用")

    def get_connection_count(self) -> int:
        """
        获取当前活跃连接数

        Returns:
            int: 活跃连接数
        """
        active_count = 0
        for ref in self._connections.copy():
            if ref() is not None:
                active_count += 1
            else:
                # 清理失效的引用
                self._connections.discard(ref)

        return active_count

    def get_connection_names(self) -> List[str]:
        """
        获取所有连接名称

        Returns:
            List[str]: 连接名称列表
        """
        names = []
        active_websockets = set()

        # 收集所有活跃的WebSocket
        for ref in self._connections:
            ws = ref()
            if ws is not None:
                active_websockets.add(ws)

        # 获取对应名称
        for ws_id, name in self._connection_names.items():
            # 这里需要检查对应的WebSocket是否还存在
            # 简化实现：返回所有名称
            names.append(name)

        return names

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            dict: 健康状态信息
        """
        active_count = 0
        closed_count = 0
        error_count = 0

        for ref in self._connections.copy():
            websocket = ref()
            if websocket is None:
                continue

            try:
                if hasattr(websocket, 'closed'):
                    if websocket.closed:
                        closed_count += 1
                    else:
                        active_count += 1
                else:
                    # 如果没有closed属性，假设是活跃的
                    active_count += 1
            except Exception:
                error_count += 1

        return {
            "total_registered": len(self._connections),
            "active_connections": active_count,
            "closed_connections": closed_count,
            "error_connections": error_count,
            "connection_names": self.get_connection_names()
        }
