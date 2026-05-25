"""
AI回复处理器
专注的AI处理，移除复杂预处理和发送逻辑
"""
import asyncio
from typing import Dict, Any, Optional
from bridge.context import Context, ContextType
from .base import BaseHandler
from .preprocessor import MessagePreprocessor
from Agent.bot import Bot

_BATCH_WINDOW = 2.5  # 秒，同一客户消息合并窗口


class AIReplyHandler(BaseHandler):
    """专注的AI回复处理器 — 支持短时消息合并（文字+图片/视频）"""

    def __init__(self, bot: Bot = None, auto_reply_types: set = None):
        super().__init__("AIReplyHandler")
        if bot is None:
            try:
                from core.di_container import container
                from Agent.CustomerAgent.custom.customer_agent import CustomerAgent
                bot = container.get(CustomerAgent)
            except Exception as e:
                from utils.logger_loguru import get_logger
                get_logger("AIReplyHandler").warning(f"从DI容器获取CustomerAgent失败: {e}, 将使用无Bot模式")
        self.bot = bot
        self.preprocessor = MessagePreprocessor()
        self.auto_reply_types = auto_reply_types or {
            ContextType.TEXT,
            ContextType.GOODS_INQUIRY,
            ContextType.GOODS_SPEC,
            ContextType.ORDER_INFO,
            ContextType.IMAGE,
            ContextType.VIDEO,
            ContextType.EMOTION
        }
        # 消息批处理：按 customer_key → (contexts_list, metadata, asyncio.Task)
        self._pending_batches: Dict[str, list] = {}

    def can_handle(self, context: Context) -> bool:
        return context.type in self.auto_reply_types

    def _customer_key(self, context: Context) -> str:
        try:
            return f"{context.channel_type}_{context.kwargs.shop_id}_{context.kwargs.from_uid}"
        except Exception:
            return "unknown"

    async def handle(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """处理AI回复 — 支持消息合并"""
        try:
            key = self._customer_key(context)

            # 如果已有待处理批次，合并进去并重置计时器
            if key in self._pending_batches:
                ctx_list, meta, task = self._pending_batches[key]
                task.cancel()
                ctx_list.append(context)
                self._pending_batches[key] = (
                    ctx_list, meta,
                    asyncio.ensure_future(self._process_batch(key))
                )
                self.logger.info(f"[BATCH] 合并消息到批次: key={key} count={len(ctx_list)}")
                return True  # 返回 True 阻止 downstream 处理

            # 新批次：创建并等待 _BATCH_WINDOW 秒
            self._pending_batches[key] = (
                [context], metadata,
                asyncio.ensure_future(self._process_batch(key))
            )
            return True  # 标记为"已接受"，实际处理在 _process_batch 中

        except Exception as e:
            self.logger.error(f"AI回复处理失败: {e}")
            return await self._handle_fallback(context, metadata)

    async def _process_batch(self, key: str) -> bool:
        """等待合并窗口结束，然后合并处理批次中的所有消息"""
        await asyncio.sleep(_BATCH_WINDOW)

        entry = self._pending_batches.pop(key, None)
        if entry is None:
            return True

        try:
            ctx_list, metadata, _task = entry

            if len(ctx_list) == 1:
                return await self._handle_single(ctx_list[0], metadata)

            # 多条消息：合并 TEXT + IMAGE/VIDEO
            self.logger.info(f"[BATCH] 合并处理 {len(ctx_list)} 条消息: key={key}")
            text_parts = []
            media_urls = []
            primary_ctx = ctx_list[0]

            for ctx in ctx_list:
                if ctx.type in (ContextType.IMAGE, ContextType.VIDEO):
                    urls = getattr(ctx, "media_urls", []) or []
                    media_urls.extend(urls)
                else:
                    c = ctx.content
                    if isinstance(c, str) and c.strip():
                        text_parts.append(c.strip())

            merged_query = " ".join(text_parts) if text_parts else (
            "客户发送了一张图片。请描述图片内容，结合当前对话上下文判断客户意图。"
            "如果图片是商品，帮客户在店铺中查找相似商品并推荐。"
        )
            return await self._handle_single(primary_ctx, metadata,
                                             override_query=merged_query,
                                             override_media_urls=media_urls)
        except Exception as e:
            self.logger.error(f"[BATCH] 合并处理失败: {e}", exc_info=True)
            return True

    async def _handle_single(self, context: Context, metadata: Dict[str, Any],
                             override_query: str = None,
                             override_media_urls: list = None) -> bool:
        """处理单条消息（或合并后的消息）"""
        try:
            user_query = override_query or (
                context.content if isinstance(context.content, str)
                else str(context.content or "")
            )
            media_info = ""
            if override_media_urls:
                media_info = f" media_urls={len(override_media_urls)}"
                context.media_urls = override_media_urls

            self.logger.info(f"[AI] 收到用户消息: shop={context.kwargs.shop_name} "
                             f"from_uid={context.kwargs.from_uid} query={user_query[:50]}{media_info}")
            processed_content = self.preprocessor.process(user_query, context.type)

            reply = await self._get_ai_reply(processed_content, context)
            if not reply:
                self.logger.warning("AI回复生成失败，使用备用回复")
                return await self._handle_fallback(context, metadata)

            if reply and "[TRANSFER_NEEDED]" in str(reply):
                reply = str(reply).replace("[TRANSFER_NEEDED]", "").strip()
                self.logger.info(f"[AI] 触发转人工：{context.type}")
                await self._send_reply(context, reply, metadata)
                await self._trigger_transfer(context)
                return True

            self.logger.info(f"[AI] 生成回复: {str(reply)[:60]}")
            success = await self._send_reply(context, reply, metadata)
            if success:
                await self.log_message(context, "AI回复发送成功", f"回复: {reply}...")
                try:
                    session_id, shop_id = self._build_session_id(context)
                    if session_id:
                        from ui.error_notifier import error_notifier
                        error_notifier.session_updated.emit(session_id, shop_id)
                except Exception as e:
                    self.logger.error(f"发送会话更新信号失败: {e}")
            else:
                self.logger.warning("AI回复发送失败")
                return await self._handle_fallback(context, metadata)

            return True

        except Exception as e:
            self.logger.error(f"AI回复处理失败: {e}")
            return await self._handle_fallback(context, metadata)

    async def _get_ai_reply(self, query: str, context: Context) -> Optional[str]:
        """获取AI回复，出错时返回 None（触发兜底回复）"""
        if not self.bot:
            return None

        try:
            # 优先使用异步接口，其次回退到同步接口
            if hasattr(self.bot, 'async_reply'):
                res = await self.bot.async_reply(query, context)
            elif hasattr(self.bot, 'reply'):
                res = self.bot.reply(query, context)
            else:
                self.logger.warning("Bot不支持reply或async_reply方法")
                return None

            # 检查是否为内部错误
            from bridge.reply import ReplyType
            if hasattr(res, 'type') and res.type == ReplyType.ERROR:
                error_msg = getattr(res, 'content', '未知错误')
                self.logger.error(f"Agent 运行出错: {error_msg}")
                self._notify_error(context, error_msg)
                return None

            return getattr(res, 'content', str(res))

        except Exception as e:
            self.logger.error(f"AI Bot调用失败: {e}")
            self._notify_error(context, str(e))
            return None

    def _build_session_id(self, context: Context):
        """从 context 提取 (session_id, shop_id)，与 CustomerAgent.async_reply() 保持一致"""
        session_id = ""
        shop_id = ""
        try:
            if context is None or not hasattr(context, 'kwargs'):
                return session_id, shop_id
            kwargs = context.kwargs
            channel_type = context.channel_type.value if context.channel_type else ""
            shop_id = str(kwargs.shop_id or "")
            customer_id = str(kwargs.from_uid or "")
            session_id = f"{channel_type}_{shop_id}_{customer_id}"
        except Exception:
            pass
        return session_id, shop_id

    def _notify_error(self, context: Context, error_msg: str):
        """通知 UI 层 Agent 出错，需要人工介入"""
        try:
            shop_name = ""
            session_id = ""
            if context and hasattr(context, 'kwargs'):
                session_id, shop_id = self._build_session_id(context)
                shop_name = str(getattr(context.kwargs, 'shop_name', ''))

            # 标记会话为错误状态
            if session_id:
                try:
                    from ui.session_ui import _get_session_manager
                    mgr = _get_session_manager()
                    mgr.mark_session_error(session_id)
                except Exception as e:
                    self.logger.error(f"标记会话错误状态失败: {e}")

            # 发射信号通知 UI 弹窗
            from ui.error_notifier import error_notifier
            error_notifier.agent_error.emit(shop_name, error_msg, session_id)
        except Exception as e:
            self.logger.error(f"发送错误通知失败: {e}")

    async def _trigger_transfer(self, context: Context):
        """触发转人工流程"""
        try:
            kwargs = context.kwargs
            shop_id = str(kwargs.shop_id or "")
            shop_name = str(kwargs.shop_name or "")
            customer_id = str(kwargs.from_uid or "")
            session_id = f"{context.channel_type}_{shop_id}_{customer_id}"

            # 标记会话需要转人工
            try:
                from ui.session_ui import _get_session_manager
                mgr = _get_session_manager()
                if hasattr(mgr, 'mark_session_needs_human'):
                    mgr.mark_session_needs_human(session_id)
            except Exception:
                pass

            # 发射转人工信号
            from ui.error_notifier import error_notifier
            error_notifier.transfer_to_human.emit(
                shop_id, shop_name, customer_id,
                "多模态转接（图片/视频）", session_id
            )
            self.logger.info(f"转人工信号已发送: shop={shop_name} customer={customer_id}")
        except Exception as e:
            self.logger.error(f"触发转人工失败: {e}")

    async def _send_reply(self, context: Context, reply: str, metadata: Dict[str, Any]) -> bool:
        """发送回复"""
        try:
            # 从metadata中提取必要信息
            shop_id = metadata.get('shop_id')
            user_id = metadata.get('user_id')
            from_uid = metadata.get('from_uid')

            if not all([shop_id, user_id, from_uid]):
                self.logger.warning(f"缺少发送信息: shop_id={shop_id}, user_id={user_id}, from_uid={from_uid}")
                return False

            # 尝试发送消息
            from Channel.pinduoduo.utils.API.send_message import SendMessage
            sender = SendMessage(shop_id, user_id)
            result = sender.send_text(from_uid, reply)
            if isinstance(result, dict) and result.get("success"):
                return True
            return False

        except Exception as e:
            self.logger.error(f"发送回复失败: {e}")
            return False

    async def _handle_fallback(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """备用回复处理"""
        try:
            # 简单的自动回复
            reply_text = "亲，感谢您的咨询，客服正在为您处理，请稍等片刻。"

            # 记录备用回复
            self.logger.info("使用备用回复")

            # 尝试发送备用回复
            success = await self._send_reply(context, reply_text, metadata)
            if not success:
                # 如果发送失败，记录日志并返回False让下游有机会处理
                await self.log_message(context, "备用回复发送失败", f"内容: {reply_text}")
                return False

            await self.log_message(context, "备用回复发送成功", f"内容: {reply_text}")
            return True

        except Exception as e:
            self.logger.error(f"备用回复处理失败: {e}")
            return True  # 即使失败也返回True，避免重复处理
