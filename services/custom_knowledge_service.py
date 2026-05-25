"""
自定义知识服务
管理 custom_knowledge 表的 CRUD，以及与向量索引的同步。
"""
from __future__ import annotations

from typing import List, Optional, Dict, TYPE_CHECKING
from datetime import datetime

from database.models import CustomKnowledge
from database.db_manager import db_manager
from utils.logger_loguru import get_logger

if TYPE_CHECKING:
    from services.vector_index_sync import VectorIndexSync
    from services.chunking_service import ChunkingService

logger = get_logger("CustomKnowledgeService")


class CustomKnowledgeService:
    """自定义知识 CRUD 服务"""

    def __init__(
        self,
        vector_sync: Optional["VectorIndexSync"] = None,
        chunking_service: Optional["ChunkingService"] = None,
    ):
        self._vector_sync = vector_sync
        self._chunking = chunking_service

    def _session(self):
        return db_manager.Session()

    def create_entry(self, shop_id: int, title: str, content: str) -> int:
        """仅入库，返回 entry.id（int，不返回 ORM 对象避免 session 分离问题）"""
        s = self._session()
        try:
            entry = CustomKnowledge(
                shop_id=shop_id,
                title=title,
                content=content,
                chunk_count=0,
            )
            s.add(entry)
            s.flush()  # flush 触发 INSERT，获取自增 ID
            entry_id = entry.id
            s.commit()
            logger.info(f"自定义知识已创建: shop_id={shop_id}, title={title}, id={entry_id}")
            return entry_id
        except Exception as e:
            s.rollback()
            logger.error(f"创建自定义知识失败: {e}")
            raise
        finally:
            s.close()

    def list_entries(self, shop_id: int) -> List[CustomKnowledge]:
        """列出店铺的所有自定义知识"""
        s = self._session()
        try:
            from sqlalchemy import select
            stmt = select(CustomKnowledge).where(
                CustomKnowledge.shop_id == shop_id
            ).order_by(CustomKnowledge.created_at.desc())
            return list(s.scalars(stmt))
        finally:
            s.close()

    def get_entry(self, entry_id: int) -> Optional[CustomKnowledge]:
        s = self._session()
        try:
            return s.get(CustomKnowledge, entry_id)
        finally:
            s.close()

    async def save_and_index(self, shop_id: int, title: str, content: str) -> Dict:
        """创建条目 + 分块 + 嵌入 + 索引

        Returns:
            {entry_id, chunk_count}
        """
        chunk_count = 0
        if self._chunking:
            chunks = self._chunking.chunk_text(content)
            chunk_count = len(chunks)

        entry_id = self.create_entry(shop_id, title, content)
        self._update_chunk_count(entry_id, chunk_count)

        if self._vector_sync:
            await self._vector_sync.index_raw(
                "custom", entry_id, shop_id,
                f"{title}\n{content}",
            )

        return {"entry_id": entry_id, "chunk_count": chunk_count}

    def _update_chunk_count(self, entry_id: int, chunk_count: int):
        s = self._session()
        try:
            entry = s.get(CustomKnowledge, entry_id)
            if entry:
                entry.chunk_count = chunk_count
                s.commit()
        finally:
            s.close()

    def delete_entry(self, entry_id: int) -> bool:
        """删除条目"""
        s = self._session()
        try:
            entry = s.get(CustomKnowledge, entry_id)
            if not entry:
                return False
            shop_id = entry.shop_id
            s.delete(entry)
            s.commit()
            logger.info(f"自定义知识已删除: id={entry_id}")
            return True
        except Exception as e:
            s.rollback()
            logger.error(f"删除自定义知识失败: {e}")
            return False
        finally:
            s.close()

    def update_entry(self, entry_id: int, title: str = None, content: str = None) -> Optional[CustomKnowledge]:
        s = self._session()
        try:
            entry = s.get(CustomKnowledge, entry_id)
            if not entry:
                return None
            if title is not None:
                entry.title = title
            if content is not None:
                entry.content = content
            s.commit()
            return entry
        except Exception as e:
            s.rollback()
            logger.error(f"更新自定义知识失败: {e}")
            return None
        finally:
            s.close()
