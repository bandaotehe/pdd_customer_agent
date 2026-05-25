"""
处理器基类和通用工具
"""
import json
from typing import Dict, Any, Optional
from utils.logger_loguru import get_logger
from bridge.context import Context
from ..core.handlers import MessageHandler



class BaseHandler(MessageHandler):
    """处理器基类，提供通用功能"""

    def __init__(self, name: Optional[str] = None):
        super().__init__()
        self.name = name or self.__class__.__name__

    async def log_message(self, context: Context, action: str, extra_info: str = ""):
        """统一的日志记录（不记录完整内容以保护隐私）"""
        user_info = self._get_user_info(context)
        content_preview = str(context.content)[:50] + "..." if context.content else ""
        self.logger.info(f"{self.name} {action} - {user_info} - {content_preview} {extra_info}")

    def _get_user_info(self, context: Context) -> str:
        """提取用户信息"""
        try:
            if hasattr(context, 'kwargs') and context.kwargs:
                from_uid = getattr(context.kwargs, 'from_uid', None)
                username = getattr(context.kwargs, 'username', None)
                if username:
                    return f"用户:{username}({from_uid})"
                elif from_uid:
                    return f"用户:{from_uid}"
            return "用户:unknown"
        except Exception:
            return "用户:unknown"