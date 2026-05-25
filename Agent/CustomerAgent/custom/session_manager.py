"""
会话历史管理模块

提供 Agent 会话历史的 SQLite 持久化和上下文压缩功能。
"""
from __future__ import annotations

import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Index,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from utils.logger_loguru import get_logger

logger = get_logger("SessionManager")

Base = declarative_base()


# ==============================================================================
# 模型定义
# ==============================================================================

class AgentMessage(Base):
    """Agent 会话消息模型"""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    shop_id = Column(String(100), nullable=True, index=True)
    role = Column(String(32), nullable=False)  # system | user | assistant | tool
    content = Column(Text, nullable=True)
    tool_call_id = Column(String(128), nullable=True)  # 关联 LLM 请求中的 tool_call id
    timestamp = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        Index("ix_agent_messages_session_timestamp", "session_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "shop_id": self.shop_id,
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Session(Base):
    """会话元数据，按店铺分组管理"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    shop_id = Column(String(100), nullable=False, index=True)
    channel_type = Column(String(50), nullable=False)
    user_id = Column(String(100), nullable=False)
    last_message_preview = Column(String(255), nullable=True)
    message_count = Column(Integer, default=0)
    is_error = Column(Boolean, default=False)
    needs_human = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "shop_id": self.shop_id,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
            "last_message_preview": self.last_message_preview,
            "message_count": self.message_count,
            "is_error": self.is_error,
            "needs_human": self.needs_human,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }


# ==============================================================================
# Token 估算
# ==============================================================================

class TokenEstimator:
    """Token 数量估算器"""

    def __init__(self, model_name: str = "gpt-4"):
        self._encoding = None
        self._available = False
        self._model_name = model_name
        self._init_encoding()

    def _init_encoding(self) -> None:
        try:
            import tiktoken
            self._encoding = tiktoken.encoding_for_model(self._model_name)
            self._available = True
            logger.debug("tiktoken 初始化成功")
        except ImportError:
            logger.warning("tiktoken 未安装，使用字符数估算 tokens")
            self._available = False
        except Exception:
            try:
                import tiktoken
                self._encoding = tiktoken.get_encoding("cl100k_base")
                self._available = True
                logger.debug("tiktoken cl100k_base 编码器初始化成功")
            except Exception as e:
                logger.warning(f"tiktoken 编码器初始化失败: {e}")
                self._available = False

    def estimate(self, text: str) -> int:
        """估算文本的 token 数量"""
        if not text:
            return 0
        if self._available and self._encoding:
            return len(self._encoding.encode(text))
        # 降级：字符数估算（中文字符 ≈ 2 tokens，英文 ≈ 0.25 tokens/字符）
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 2 + other_chars * 0.25)

    def estimate_messages(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的总 token 数量"""
        total = 0
        for msg in messages:
            # 每个消息有 role overhead
            total += 4  # approximate per-message overhead
            if msg.get("content"):
                total += self.estimate(str(msg["content"]))
            if msg.get("tool_calls"):
                total += self.estimate(str(msg["tool_calls"]))
        return total


# ==============================================================================
# SessionManager
# ==============================================================================

class SessionManager:
    """
    会话历史管理器

    提供：
    - 消息持久化（SQLite）
    - 历史加载和追加
    - 基于 token_window 的上下文压缩
    """

    def __init__(
        self,
        db_path: str,
        token_window: int = 131072,
        compress_ratio: float = 0.7,
        retain_count: int = 5,
        model_name: str = "gpt-4",
    ):
        """
        Args:
            db_path: SQLite 数据库文件路径
            token_window: 模型 context window 大小（默认 128k = 131072）
            compress_ratio: 压缩触发比例（默认 0.7，即超过 70% 时触发）
            retain_count: 压缩后保留的最近消息条数
            model_name: 用于 tiktoken 的模型名称
        """
        self.db_path = db_path
        self.token_window = token_window
        self.compress_ratio = compress_ratio
        self.retain_count = retain_count
        self.threshold = int(token_window * compress_ratio)

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        self._Session = sessionmaker(bind=self.engine)

        # 迁移：为旧版 agent_messages 表添加 shop_id 列
        try:
            with self.engine.connect() as conn:
                conn.execute(text("ALTER TABLE agent_messages ADD COLUMN shop_id VARCHAR(100)"))
                conn.commit()
                logger.info("已为 agent_messages 添加 shop_id 列")
        except Exception:
            pass  # 列已存在

        # 迁移：为旧版 sessions 表添加 is_error 列
        try:
            with self.engine.connect() as conn:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN is_error BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("已为 sessions 添加 is_error 列")
        except Exception:
            pass  # 列已存在

        # 迁移：为旧版 sessions 表添加 needs_human 列
        try:
            with self.engine.connect() as conn:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN needs_human BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("已为 sessions 添加 needs_human 列")
        except Exception:
            pass  # 列已存在

        Base.metadata.create_all(self.engine)

        self._token_estimator = TokenEstimator(model_name=model_name)
        logger.info(
            f"SessionManager 初始化完成: db={db_path}, "
            f"threshold={self.threshold}, retain={retain_count}"
        )

    def _session(self):
        return self._Session()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: Optional[str] = None,
        shop_id: Optional[str] = None,
        channel_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """追加消息到会话历史，并更新会话元数据"""
        s = self._session()
        try:
            msg = AgentMessage(
                session_id=session_id,
                shop_id=shop_id,
                role=role,
                content=content,
                tool_call_id=tool_call_id,
                timestamp=datetime.now(),
            )
            s.add(msg)

            # 更新会话元数据
            if shop_id:
                existing = s.query(Session).filter(
                    Session.session_id == session_id
                ).first()
                if existing:
                    existing.message_count = existing.message_count + 1
                    existing.last_activity_at = datetime.now()
                    if content and role in ("user", "assistant"):
                        existing.last_message_preview = content[:100].replace("\n", " ")
                else:
                    ch_type = channel_type or "unknown"
                    uid = user_id or session_id
                    s.add(Session(
                        session_id=session_id,
                        shop_id=shop_id,
                        channel_type=ch_type,
                        user_id=uid,
                        message_count=1,
                        last_message_preview=(content[:100].replace("\n", " ") if content else None),
                    ))

            s.commit()
            return True
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"添加消息失败: {e}")
            return False
        finally:
            s.close()

    def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取会话历史消息（按时间升序）"""
        session = self._session()
        try:
            query = session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).order_by(AgentMessage.timestamp.asc())

            if limit is not None:
                query = query.limit(limit)

            messages = query.all()
            return [msg.to_dict() for msg in messages]
        except SQLAlchemyError as e:
            logger.error(f"获取历史消息失败: {e}")
            return []
        finally:
            session.close()

    def get_message_count(self, session_id: str) -> int:
        """获取会话消息总数"""
        session = self._session()
        try:
            return session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).count()
        except SQLAlchemyError as e:
            logger.error(f"获取消息数量失败: {e}")
            return 0
        finally:
            session.close()

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 数量"""
        return self._token_estimator.estimate_messages(messages)

    def should_compress(self, session_id: str) -> bool:
        """检查是否需要压缩"""
        messages = self.get_history(session_id)
        if not messages:
            return False
        token_count = self.estimate_tokens(messages)
        return token_count > self.threshold

    def compress_history(
        self,
        session_id: str,
        llm_callable,  # 可调用的 LLM 函数，接收消息列表返回摘要字符串
        shop_id: Optional[str] = None,
    ) -> bool:
        """
        压缩会话历史：保留最近 N 条 + 生成摘要

        Args:
            session_id: 会话 ID
            llm_callable: 接受 messages 列表，返回摘要字符串的可调用对象

        Returns:
            压缩是否成功
        """
        session = self._session()
        try:
            # 1. 获取全部历史
            messages = session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).order_by(AgentMessage.timestamp.asc()).all()

            if len(messages) <= self.retain_count + 1:
                logger.debug(f"消息数量 {len(messages)} 未达到压缩阈值，跳过")
                return False

            # 2. 分离要压缩的旧消息和要保留的新消息
            old_messages = messages[:-self.retain_count]
            retain_messages = messages[-self.retain_count:]

            # 3. 生成摘要
            summary_input = [
                {
                    "role": msg.role,
                    "content": msg.content,
                }
                for msg in old_messages
            ]

            try:
                summary = llm_callable(summary_input)
            except Exception as e:
                logger.error(f"生成摘要失败: {e}")
                # 摘要生成失败时，保留最近的消息，删除更旧的
                summary = "[历史消息已清理，无法生成摘要]"

            # 4. 删除旧消息
            for msg in old_messages:
                session.delete(msg)

            # 5. 在顶部插入摘要消息
            summary_msg = AgentMessage(
                session_id=session_id,
                shop_id=shop_id,
                role="system",
                content=f"[以下是对之前对话的摘要]\n\n{summary}",
                tool_call_id=None,
                timestamp=datetime.now(),
            )
            session.add(summary_msg)

            # 6. 更新保留消息的时间戳（保持顺序）
            # 保留消息已经在数据库中，无需移动

            session.commit()
            logger.info(
                f"压缩完成: session={session_id}, "
                f"删除={len(old_messages)} 条, 保留={len(retain_messages)} 条"
            )
            return True

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"压缩历史失败: {e}")
            return False
        finally:
            session.close()

    # ===== 会话管理查询方法 =====

    def get_sessions_by_shop(self, shop_id: str) -> List[Dict[str, Any]]:
        """获取某店铺的所有会话（按最近活动降序）"""
        s = self._session()
        try:
            rows = s.query(Session).filter(
                Session.shop_id == shop_id
            ).order_by(Session.last_activity_at.desc()).all()
            return [row.to_dict() for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"获取店铺会话失败: {e}")
            return []
        finally:
            s.close()

    def get_all_session_shops(self) -> List[Dict[str, Any]]:
        """获取所有有会话的店铺 ID（去重）"""
        s = self._session()
        try:
            rows = s.query(
                Session.shop_id,
                Session.channel_type,
            ).distinct().all()
            seen = set()
            result = []
            for shop_id, channel_type in rows:
                if shop_id and shop_id not in seen:
                    seen.add(shop_id)
                    result.append({"shop_id": shop_id, "channel_type": channel_type})
            return result
        except SQLAlchemyError as e:
            logger.error(f"获取会话店铺列表失败: {e}")
            return []
        finally:
            s.close()

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话元数据"""
        s = self._session()
        try:
            row = s.query(Session).filter(
                Session.session_id == session_id
            ).first()
            return row.to_dict() if row else None
        except SQLAlchemyError as e:
            logger.error(f"获取会话信息失败: {e}")
            return None
        finally:
            s.close()

    def mark_session_error(self, session_id: str) -> bool:
        """标记会话为错误状态"""
        s = self._session()
        try:
            row = s.query(Session).filter(
                Session.session_id == session_id
            ).first()
            if row:
                row.is_error = True
                s.commit()
            return True
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"标记会话错误状态失败: {e}")
            return False
        finally:
            s.close()

    def mark_session_needs_human(self, session_id: str) -> bool:
        """标记会话需要人工处理"""
        s = self._session()
        try:
            row = s.query(Session).filter(
                Session.session_id == session_id
            ).first()
            if row:
                row.needs_human = True
                s.commit()
            return True
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"标记会话转人工状态失败: {e}")
            return False
        finally:
            s.close()

    def unmark_session_needs_human(self, session_id: str) -> bool:
        """取消会话的人工处理标记"""
        s = self._session()
        try:
            row = s.query(Session).filter(
                Session.session_id == session_id
            ).first()
            if row:
                row.needs_human = False
                s.commit()
            return True
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"取消会话转人工标记失败: {e}")
            return False
        finally:
            s.close()

    def update_message_content(self, session_id: str, old_content: str, new_content: str) -> bool:
        """更新会话中指定消息的内容"""
        s = self._session()
        try:
            row = s.query(AgentMessage).filter(
                AgentMessage.session_id == session_id,
                AgentMessage.content == old_content,
            ).first()
            if row:
                row.content = new_content
                s.commit()
                return True
            return False
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"更新消息内容失败: {e}")
            return False
        finally:
            s.close()

    def get_session_needs_human(self, session_id: str) -> bool:
        """检查会话是否需要人工处理"""
        s = self._session()
        try:
            row = s.query(Session).filter(
                Session.session_id == session_id
            ).first()
            return row.needs_human if row else False
        except SQLAlchemyError as e:
            logger.error(f"查询转人工状态失败: {e}")
            return False
        finally:
            s.close()

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息"""
        s = self._session()
        try:
            s.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).delete()
            s.query(Session).filter(
                Session.session_id == session_id
            ).delete()
            s.commit()
            return True
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(f"删除会话失败: {e}")
            return False
        finally:
            s.close()
