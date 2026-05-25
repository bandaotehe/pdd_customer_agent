# 连接管理模块
import asyncio
import websockets
from websockets import exceptions as ws_exceptions
from typing import Optional, Any
from utils.logger_loguru import get_logger


class ConnectionMixin:
    """连接管理 Mixin"""

    base_url: str = "wss://m-ws.pinduoduo.com/"

    async def _connect_with_retry(self, shop_id: str, user_id: str, username: str, on_success: callable, on_failure: callable):
        """带重连机制的WebSocket连接"""
        logger = get_logger("PDDChannel")

        for attempt in range(self.reconnect_config.max_attempts):
            if self._stop_event and self._stop_event.is_set():
                logger.info(f"收到停止信号，取消重连: {shop_id}-{username}")
                self.status_manager.update_status(shop_id, user_id, username, ConnectionState.DISCONNECTED)
                return

            try:
                if attempt > 0:
                    self.status_manager.update_status(shop_id, user_id, username, ConnectionState.RECONNECTING)
                    logger.info(f"尝试重连 ({attempt + 1}/{self.reconnect_config.max_attempts}): {shop_id}-{username}")

                await self.init(shop_id, user_id, username, on_success, on_failure)
                return

            except Exception as e:
                if self._stop_event and self._stop_event.is_set():
                    logger.info(f"连接被停止信号中断: {shop_id}-{username}")
                    self.status_manager.update_status(shop_id, user_id, username, ConnectionState.DISCONNECTED)
                    return

                if attempt == self.reconnect_config.max_attempts - 1:
                    self.status_manager.update_status(shop_id, user_id, username, ConnectionState.ERROR, str(e))
                    logger.error(f"连接失败，已达到最大重试次数: {shop_id}-{username}, 错误: {str(e)}")
                    on_failure(f"连接失败，已达到最大重试次数: {e}")
                    return

                delay = min(
                    self.reconnect_config.initial_delay * (self.reconnect_config.backoff_factor ** attempt),
                    self.reconnect_config.max_delay
                )

                logger.warning(f"连接失败，{delay:.1f}秒后重试: {shop_id}-{username}, 错误: {str(e)}")

                try:
                    for _ in range(int(delay * 10)):
                        if self._stop_event and self._stop_event.is_set():
                            logger.info(f"重连延迟被停止信号中断: {shop_id}-{username}")
                            self.status_manager.update_status(shop_id, user_id, username, ConnectionState.DISCONNECTED)
                            return
                        await asyncio.sleep(0.1)
                except (asyncio.CancelledError, RuntimeError):
                    logger.info(f"重连延迟被中断或事件循环关闭: {shop_id}-{username}")
                    self.status_manager.update_status(shop_id, user_id, username, ConnectionState.DISCONNECTED)
                    return

    async def _connect_single_attempt(self, shop_id: str, user_id: str, username: str, on_success: callable, on_failure: callable):
        """单次WebSocket连接尝试（无重试时的 fallback）"""
        try:
            await self.init(shop_id, user_id, username, on_success, on_failure)
        except Exception as e:
            self.logger.warning(f"单次连接失败: {shop_id}-{username}, 错误: {str(e)}")
            on_failure(str(e))

    def _is_ws_closed(self, ws: Any) -> bool:
        """检查WebSocket是否已关闭"""
        try:
            closed = getattr(ws, "closed", None)
            if isinstance(closed, bool):
                return closed
            return False
        except Exception:
            return False

    async def _safe_close_websocket(self, ws: Any):
        """安全关闭WebSocket"""
        try:
            close_fn = getattr(ws, "close", None)
            if close_fn:
                result = close_fn()
                if asyncio.iscoroutine(result):
                    await result
        except Exception as e:
            self.logger.debug(f"关闭WebSocket失败: {e}")


# 延迟导入避免循环依赖
from core.connection_status import ConnectionState
__all__ = ['ConnectionMixin']
