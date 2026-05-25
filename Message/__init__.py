"""
Message模块重构版入口
保持向后兼容性的同时简化架构
"""

# 核心模块 - 新的简化实现
from .core.queue import SimpleMessageQueue, queue_manager
from .core.consumer import MessageConsumer, message_consumer_manager
from .core.handlers import MessageHandler, TypeBasedHandler, ChannelBasedHandler, CatchAllHandler

# 模型
from .message import ChatMessage
from .models.queue_models import MessageWrapper, QueueStats

# 处理器 - 新的模块化实现
from .handlers.base import BaseHandler
from .handlers.ai_handler import AIReplyHandler
from .handlers.preprocessor import MessagePreprocessor

# 管理器 - 直接使用核心队列管理器
from .core.queue import QueueManager

# 上下文相关
from bridge.context import Context, ContextType, ChannelType


# ============================================================================
# 向后兼容的便捷函数
# ============================================================================

def init_message_system():
    """初始化消息系统"""
    return queue_manager, message_consumer_manager


def create_queue(name: str, max_size: int = 1000) -> SimpleMessageQueue:
    """创建消息队列（兼容原API）"""
    from .models.queue_models import QueueConfig
    config = QueueConfig(max_size=max_size)
    return queue_manager.get_or_create_queue(name, config)


def create_consumer(queue_name: str, max_concurrent: int = 10) -> MessageConsumer:
    """创建消息消费者（兼容原API）"""
    return message_consumer_manager.create_consumer(queue_name, max_concurrent)


def get_queue(name: str) -> SimpleMessageQueue:
    """获取消息队列（兼容原API）"""
    return queue_manager.get_queue(name)


def get_consumer(queue_name: str) -> MessageConsumer:
    """获取消息消费者（兼容原API）"""
    return message_consumer_manager.get_consumer(queue_name)


async def start_consumer(queue_name: str):
    """启动消息消费者（兼容原API）"""
    await message_consumer_manager.start_consumer(queue_name)


async def stop_consumer(queue_name: str):
    """停止消息消费者（兼容原API）"""
    await message_consumer_manager.stop_consumer(queue_name)


async def put_message(queue_name: str, context: Context) -> str:
    """向队列放入消息（兼容原API）"""
    queue = queue_manager.get_or_create_queue(queue_name)
    return await queue.put(context)


async def get_message(queue_name: str, timeout: float = None):
    """从队列获取消息（兼容原API）"""
    queue = queue_manager.get_queue(queue_name)
    if queue:
        return await queue.get(timeout)
    return None


# ============================================================================
# 便捷的处理器创建函数
# ============================================================================

def create_ai_handler(bot=None) -> AIReplyHandler:
    """创建AI回复处理器"""
    return AIReplyHandler(bot)


def create_simple_handlers() -> list:
    """创建简单处理器列表"""
    # TODO: 实现或导入 SimpleReplyHandler, TextOnlyHandler, LoggingHandler
    return []


def create_comprehensive_handlers(bot=None) -> list:
    """创建全面的处理器列表"""
    handlers = []
    if bot:
        handlers.insert(0, AIReplyHandler(bot))
    return handlers


# ============================================================================
# 兼容性映射（将新的类映射到旧的API）
# ============================================================================

# 为了向后兼容，将新的类映射到旧的名称
MessageQueue = SimpleMessageQueue
MessageQueueManager = QueueManager

# 关键词检测处理器缓存（避免每次实例化都查 DB）
_cached_keyword_handler = None


def _get_keyword_handler():
    """获取或创建缓存的关键词检测处理器"""
    global _cached_keyword_handler
    if _cached_keyword_handler is None:
        try:
            from .handlers.keyword_handler import KeywordDetectionHandler
            _cached_keyword_handler = KeywordDetectionHandler()
        except ImportError as e:
            from utils.logger_loguru import get_logger
            get_logger("handler_chain").warning(f"关键词检测处理器导入失败: {e}")
    return _cached_keyword_handler


# 提供兼容的handler_chain函数实现
def handler_chain(use_ai=True, businessHours=None, bot=None):
    """简化版处理器链创建函数 - 包含关键词检测"""
    handlers = []

    # 1. 首先检查关键词（最高优先级，缓存实例避免重复 DB 查询）
    keyword_handler = _get_keyword_handler()
    if keyword_handler is not None:
        handlers.append(keyword_handler)

    # 2. 如果启用AI，添加AI处理器
    if use_ai:
        handlers.append(create_ai_handler(bot))

    # 3. 最后添加兜底处理器
    handlers.append(CatchAllHandler())

    return handlers


# ============================================================================
# 导出所有主要类和函数（保持向后兼容）
# ============================================================================

__all__ = [
    # 核心类
    'MessageQueue',
    'MessageQueueManager',
    'MessageHandler',
    'MessageConsumer',
    'MessageConsumerManager',
    'TypeBasedHandler',
    'ChannelBasedHandler',
    'ChatMessage',
    'Context',
    'ContextType',
    'ChannelType',
    'MessageWrapper',
    'QueueStats',
    'CatchAllHandler',

    # 管理器
    'queue_manager',
    'message_consumer_manager',
    'QueueManager',

    # 处理器类
    'BaseHandler',
    'AIReplyHandler',
    'MessagePreprocessor',
    'KeywordDetectionHandler',

    # 便捷函数
    'init_message_system',
    'create_queue',
    'create_consumer',
    'get_queue',
    'get_consumer',
    'start_consumer',
    'stop_consumer',
    'put_message',
    'get_message',
    'create_ai_handler',
    'create_simple_handlers',
    'create_comprehensive_handlers',
    'handler_chain'  # 提供兼容的handler_chain函数
]
