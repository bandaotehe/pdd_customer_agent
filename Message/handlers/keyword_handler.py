"""
关键词检测处理器 - 检测转人工关键词并触发转人工流程
"""
from typing import Dict, Any
from bridge.context import Context, ContextType
from .base import BaseHandler
from database.db_manager import db_manager
from utils.logger_loguru import get_logger
from Channel.pinduoduo.utils.API.send_message import SendMessage
from Agent.CustomerAgent.tools.move_conversation import transfer_conversation, TransferConversationParams

class KeywordDetectionHandler(BaseHandler):
    """关键词检测处理器 - 检测转人工关键词并触发转人工流程"""

    def __init__(self):
        super().__init__("KeywordDetectionHandler")
        self.logger = get_logger("KeywordDetectionHandler")
        self.keywords = self._load_keywords()

        # 记录加载的关键词数量
        self.logger.info(f"关键词检测处理器初始化完成，加载了 {len(self.keywords)} 个关键词")

    def _load_keywords(self):
        """从数据库加载关键词"""
        try:
            keywords_data = db_manager.get_all_keywords()
            keywords = {item['keyword'].lower() for item in keywords_data if item.get('keyword')}
            self.logger.debug(f"从数据库加载关键词: {keywords}")
            return keywords
        except Exception as e:
            self.logger.error(f"加载关键词失败: {e}")
            # 如果加载失败，使用默认关键词
            default_keywords = {
                "转人工", "人工客服", "真人", "客服", "人工", "工单", "好评",
                "取消订单", "改地址", "转售后客服", "转售后", "返现", "过敏",
                "退款", "没有效果", "骗人", "投诉", "纠纷", "开发票", "开票",
                "烂", "取消", "备注"
            }
            self.logger.warning(f"使用默认关键词: {default_keywords}")
            return default_keywords

    def can_handle(self, context: Context) -> bool:
        """检查消息是否包含关键词"""
        # 只处理文本类型的消息
        if context.type != ContextType.TEXT:
            return False

        # 检查消息内容是否存在且为字符串
        if not context.content or not isinstance(context.content, str):
            return False

        # 将消息内容转换为小写进行检测
        content_lower = context.content.lower()

        # 检查是否包含任何关键词
        for keyword in self.keywords:
            if keyword in content_lower:
                self.logger.debug(f"检测到关键词: '{keyword}' 在消息: '{context.content}'")
                return True

        return False

    async def handle(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """检测到转人工关键词：回复客户确认消息 + 通知管理员"""
        try:
            kwargs = context.kwargs
            shop_id = getattr(kwargs, 'shop_id', None) or (kwargs.get('shop_id') if isinstance(kwargs, dict) else None)
            user_id = getattr(kwargs, 'user_id', None) or (kwargs.get('user_id') if isinstance(kwargs, dict) else None)
            from_uid = getattr(kwargs, 'from_uid', None) or (kwargs.get('from_uid') if isinstance(kwargs, dict) else None)

            if not all([shop_id, user_id, from_uid]):
                return False

            # Step 1: 先给客户发送确认消息
            try:
                sender = SendMessage(shop_id, user_id)
                sender.send_text(from_uid, "已收到您的请求，售后专员将尽快处理您的问题，请稍候。")
            except Exception as e:
                self.logger.error(f"发送转接确认消息失败: {e}")

            # Step 2: 执行实际的会话转接
            transfer_ok = False
            try:
                params = TransferConversationParams(
                    shop_id=shop_id,
                    user_id=user_id,
                    recipient_uid=from_uid,
                )
                result = transfer_conversation(params)
                self.logger.info(f"[关键词转接] shop={shop_id} uid={from_uid} 结果: {result}")
                transfer_ok = "成功" in str(result)
            except Exception as e:
                self.logger.error(f"[关键词转接] 调用 transfer_conversation 异常: {e}")

            # Step 3: 转接失败时发送安抚消息
            if not transfer_ok:
                try:
                    sender = SendMessage(shop_id, user_id)
                    sender.send_text(from_uid, "亲，目前售后专员暂时不在线，建议您稍后再联系我们哦")
                except Exception as e:
                    self.logger.error(f"发送转接失败安抚消息失败: {e}")

            # 通知管理员
            try:
                from ui.error_notifier import error_notifier
                channel_type = context.channel_type.value if context.channel_type else ""
                session_id = f"{channel_type}_{shop_id}_{from_uid}"
                shop_name = getattr(kwargs, 'shop_name', '') or (
                    kwargs.get('shop_name', '') if isinstance(kwargs, dict) else ''
                )

                # 标记会话需要人工处理
                from ui.session_ui import _get_session_manager
                mgr = _get_session_manager()
                mgr.mark_session_needs_human(session_id)
                # 保存 Agent 确认消息"这条消息需人工回复"
                mgr.add_message(
                    session_id=session_id,
                    role="assistant",
                    content="这条消息需人工回复",
                    shop_id=str(shop_id),
                    channel_type=channel_type,
                    user_id=str(from_uid),
                )

                error_notifier.transfer_to_human.emit(
                    str(shop_id), str(shop_name), str(from_uid), "人工客服", session_id
                )
            except Exception as e:
                self.logger.error(f"发送转人工通知失败: {e}")

            return True

        except Exception as e:
            self.logger.error(f"转人工处理失败: {e}")
            return False

    def reload_keywords(self) -> None:
        """重新加载关键词（用于管理员更新关键词后刷新）"""
        old_count = len(self.keywords)
        self.keywords = self._load_keywords()
        new_count = len(self.keywords)
        self.logger.info(f"关键词重新加载完成: {old_count} -> {new_count}")

    def get_keyword_count(self) -> int:
        """获取当前关键词数量"""
        return len(self.keywords)

    def get_keywords(self) -> set:
        """获取当前关键词列表"""
        return self.keywords.copy()