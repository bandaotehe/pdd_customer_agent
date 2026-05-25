"""
简化的消息处理器基类
提取核心接口，移除复杂的实现
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from bridge.context import Context
from utils.logger_loguru import get_logger


class MessageHandler(ABC):
    """消息处理器基类"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def can_handle(self, context: Context) -> bool:
        """
        判断是否能处理该消息

        Args:
            context: Context格式的消息

        Returns:
            bool: 是否能处理
        """
        pass

    @abstractmethod
    async def handle(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """
        处理消息

        Args:
            context: Context格式的消息
            metadata: 消息元数据

        Returns:
            bool: 是否处理成功
        """
        pass

    async def on_error(self, context: Context, error: Exception) -> None:
        """
        错误处理回调（可选重写）

        Args:
            context: 消息上下文
            error: 错误对象
        """
        self.logger.error(f"Handler {self.__class__.__name__} error: {error}")


class TypeBasedHandler(MessageHandler):
    """基于消息类型的处理器"""

    def __init__(self, supported_types: set):
        super().__init__()
        self.supported_types = supported_types

    def can_handle(self, context: Context) -> bool:
        """检查消息类型"""
        return context.type in self.supported_types


class ChannelBasedHandler(MessageHandler):
    """基于渠道类型的处理器"""

    def __init__(self, supported_channels: set):
        super().__init__()
        self.supported_channels = supported_channels

    def can_handle(self, context: Context) -> bool:
        """检查渠道类型"""
        # 处理 channel_type 可能为 None 的情况
        channel_type = context.channel_type
        if channel_type is None:
            return False

        # 支持字符串和枚举类型
        if hasattr(channel_type, 'value'):
            channel_str = str(channel_type.value)
        else:
            channel_str = str(channel_type)

        return channel_str in {str(ch) for ch in self.supported_channels}


class CatchAllHandler(MessageHandler):
    """兜底处理器 - 处理所有未被其他处理器处理的消息"""

    def __init__(self):
        super().__init__()

    def can_handle(self, context: Context) -> bool:
        """总是返回True，确保能处理所有消息"""
        return True

    async def handle(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """记录所有消息，用于调试和统计（不记录完整内容以保护隐私）"""
        user_id = metadata.get('user_id', 'unknown')
        message_id = metadata.get('message_id', 'unknown')
        content_preview = str(context.content)[:50] + "..." if context.content else ""

        self.logger.info(f"=== 消息处理记录 ===")
        self.logger.info(f"用户ID: {user_id}")
        self.logger.info(f"消息ID: {message_id}")
        self.logger.info(f"消息类型: {context.type}")
        self.logger.info(f"渠道类型: {context.channel_type}")
        self.logger.info(f"消息内容预览: {content_preview}")
        self.logger.info(f"消息已被CatchAllHandler处理")
        self.logger.info(f"===================")

        return True  # 总是返回True，避免"没有合适的处理器"警告