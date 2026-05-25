"""
自动回复聊天机器人抽象类
"""


from typing import Optional
import asyncio
from bridge.context import Context
from bridge.reply import Reply


class Bot(object):
    def reply(self, query, context: Optional[Context] = None) -> Reply:
        """
        bot auto-reply content
        :param req: received message
        :return: reply content
        """
        raise NotImplementedError
        
    async def async_reply(self, query, context: Optional[Context] = None) -> Reply:
        """
        bot async auto-reply content
        :param query: received message
        :param context: context information
        :return: reply content
        """
        # 默认实现，调用同步方法
        return self.reply(query, context)