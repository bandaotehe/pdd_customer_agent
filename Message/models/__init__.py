"""
Message模块数据模型
"""

# 导入根目录的message.py
from ..message import ChatMessage
from .queue_models import MessageWrapper, QueueStats

__all__ = [
    'ChatMessage',
    'MessageWrapper',
    'QueueStats'
]