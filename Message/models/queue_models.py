"""
队列相关的数据模型
简化的消息包装器和统计信息
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from bridge.context import Context


@dataclass
class MessageWrapper:
    """消息包装器 - 简化版"""
    message_id: str
    context: Context
    timestamp: float
    retry_count: int = 0

    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = time.time()

    def to_metadata(self) -> Dict[str, Any]:
        """转换为元数据字典"""
        return {
            'message_id': self.message_id,
            'timestamp': self.timestamp,
            'retry_count': self.retry_count
        }


@dataclass
class QueueStats:
    """队列统计信息 - 简化版"""
    total_enqueued: int = 0
    total_dequeued: int = 0
    current_size: int = 0
    last_activity: Optional[float] = None

    def enqueue(self):
        """记录入队操作"""
        self.total_enqueued += 1
        self.current_size += 1
        self.last_activity = time.time()

    def dequeue(self):
        """记录出队操作"""
        self.total_dequeued += 1
        if self.current_size > 0:
            self.current_size -= 1
        self.last_activity = time.time()


@dataclass
class QueueConfig:
    """队列配置 - 简化版"""
    max_size: int = 1000
    enable_deduplication: bool = True
    deduplication_window: int = 300  # 5分钟

    def __post_init__(self):
        if self.max_size <= 0:
            raise ValueError("max_size must be positive")