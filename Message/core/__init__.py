"""
Message模块核心功能
包含简化的消息队列、消费者和处理器基类
"""

from .queue import SimpleMessageQueue, QueueManager
from .consumer import MessageConsumer
from .handlers import MessageHandler, TypeBasedHandler, ChannelBasedHandler

__all__ = [
    'SimpleMessageQueue',
    'QueueManager',
    'MessageConsumer',
    'MessageHandler',
    'TypeBasedHandler',
    'ChannelBasedHandler'
]