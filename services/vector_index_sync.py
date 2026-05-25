"""
向量索引同步服务
负责 SQL 表 → Chroma + BM25 的迁移和增量同步。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, TYPE_CHECKING

from utils.logger_loguru import get_logger

if TYPE_CHECKING:
    from database.knowledge_service import KnowledgeService
    from database.models import ProductKnowledge, CustomerServiceKnowledge
    from services.vector_store import VectorStore
    from services.bm25_index import BM25Index
    from services.embedding_service import EmbeddingService
    from services.chunking_service import ChunkingService

logger = get_logger("VectorIndexSync")


@dataclass
class SyncProgress:
    total: int = 0
    current: int = 0
    success: int = 0
    failed: int = 0
    current_name: str = ""
    source_type: str = ""
    phase: str = ""


class VectorIndexSync:
    """向量索引同步管理器"""

    _SOURCE_TYPES = ["product", "customer_service"]

    def __init__(
        self,
        vector_store: "VectorStore",
        bm25_index: "BM25Index",
        embedding_service: "EmbeddingService",
        chunking_service: "ChunkingService",
    ):
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._embedding = embedding_service
        self._chunking = chunking_service
        self._knowledge_service = None  # lazy set

    def set_knowledge_service(self, ks):
        self._knowledge_service = ks

    # ===== 全量迁移 =====

    async def migrate_all(
        self,
        shop_id: int,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None,
        batch_size: int = 50,
    ) -> Dict[str, int]:
        """迁移店铺的所有产品知识和客服知识到向量库

        Returns:
            {total, succeeded, failed}
        """
        if not self._knowledge_service:
            raise RuntimeError("knowledge_service 未注入")

        ks = self._knowledge_service
        products = ks.list_products_by_shop(shop_id)
        cs_list = ks.list_customer_service_with_disabled(shop_id)
        cs_enabled = [cs for cs in cs_list if cs.enabled]

        all_items = (
            [("product", p) for p in products if p.extracted_content] +
            [("customer_service", cs) for cs in cs_enabled if cs.content]
        )

        total = len(all_items)
        succeeded = 0
        failed = 0

        for i, (source_type, item) in enumerate(all_items):
            if progress_callback:
                progress_callback(SyncProgress(
                    total=total, current=i + 1, success=succeeded,
                    failed=failed,
                    current_name=getattr(item, 'goods_name', None) or getattr(item, 'title', ''),
                    source_type=source_type,
                    phase="migrating",
                ))

            try:
                if source_type == "product":
                    await self.index_product(item)
                else:
                    await self.index_customer_service(item)
                succeeded += 1
            except Exception as e:
                logger.error(f"迁移失败 [{source_type}]: {e}")
                failed += 1

            # 批次间短暂停顿
            if i > 0 and i % batch_size == 0:
                await asyncio.sleep(0.1)

        logger.info(f"迁移完成: shop_id={shop_id}, succeeded={succeeded}, failed={failed}")
        return {"total": total, "succeeded": succeeded, "failed": failed}

    # ===== 增量索引 =====

    async def index_product(self, product) -> bool:
        """为单个产品知识构建向量索引"""
        if not product.extracted_content:
            return False

        source_id = product.id
        shop_id = product.shop_id
        text = f"{product.goods_name}\n{product.extracted_content}"

        return await self._index_item(
            source_type="product", source_id=source_id, shop_id=shop_id,
            text=text, goods_id=product.goods_id,
        )

    async def index_customer_service(self, cs) -> bool:
        """为单个客服知识构建向量索引"""
        if not cs.content:
            return False

        source_id = cs.id
        shop_id = cs.shop_id
        text = f"{cs.title}\n{cs.content}"

        return await self._index_item(
            source_type="customer_service", source_id=source_id, shop_id=shop_id,
            text=text,
        )

    async def index_custom_entry(self, entry) -> bool:
        """为自定义知识构建向量索引"""
        if not entry.content:
            return False

        source_id = entry.id
        shop_id = entry.shop_id
        text = f"{entry.title}\n{entry.content}"

        return await self._index_item(
            source_type="custom", source_id=source_id, shop_id=shop_id,
            text=text,
        )

    async def index_raw(
        self, source_type: str, source_id: int, shop_id: int,
        text: str, **extra_meta,
    ) -> bool:
        """基于原始值构建向量索引（不依赖 ORM 对象，可在后台线程安全调用）"""
        return await self._index_item(
            source_type=source_type, source_id=source_id, shop_id=shop_id,
            text=text, **extra_meta,
        )

    async def _index_item(
        self, source_type: str, source_id: int, shop_id: int,
        text: str, **extra_meta,
    ) -> bool:
        """通用索引：分块 → 嵌入 → 存储"""
        chunks = self._chunking.chunk_text(text)
        if not chunks:
            return False

        # 嵌入
        embeddings = await self._embedding.embed(chunks)

        # 构建 ID 和 metadata
        ids = [f"{source_type}:{source_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "shop_id": shop_id,
                "source_id": source_id,
                "source_type": source_type,
                "chunk_index": i,
                "id": f"{source_type}:{source_id}:{i}",
                "text": chunks[i],
                **extra_meta,
            }
            for i in range(len(chunks))
        ]

        # 先删除旧的
        col_name = self._collection_name(source_type)
        try:
            self._vector_store.delete_by_filter(col_name, {
                "shop_id": shop_id,
                "source_id": source_id,
            })
        except Exception:
            pass

        # 写入向量库
        self._vector_store.add_documents(col_name, ids, embeddings, metadatas, chunks)

        # 重建 BM25 索引（整体重建该 source_type + shop_id 的索引）
        await self._rebuild_bm25_for_shop(source_type, shop_id)

        logger.debug(f"索引已更新: {source_type}:{source_id}, chunks={len(chunks)}")
        return True

    async def _rebuild_bm25_for_shop(self, source_type: str, shop_id: int):
        """重建某个 source_type + shop_id 的 BM25 索引"""
        col_name = self._collection_name(source_type)
        where = {"shop_id": shop_id}

        # 从 Chroma 读取所有文档
        try:
            col = self._vector_store._client.get_collection(col_name)
            result = col.get(where=where, include=["documents", "metadatas"])
            if result["ids"]:
                self._bm25.build_index(
                    source_type=source_type,
                    shop_id=shop_id,
                    documents=result["documents"],
                    metadatas=result["metadatas"],
                )
        except Exception as e:
            logger.error(f"重建 BM25 索引失败 [{source_type}:{shop_id}]: {e}")

    # ===== 删除 =====

    async def remove_product(self, product_id: int, shop_id: int) -> None:
        self._vector_store.delete_by_filter("product_knowledge", {
            "shop_id": shop_id, "source_id": product_id,
        })
        await self._rebuild_bm25_for_shop("product", shop_id)

    async def remove_customer_service(self, cs_id: int, shop_id: int) -> None:
        self._vector_store.delete_by_filter("customer_service_knowledge", {
            "shop_id": shop_id, "source_id": cs_id,
        })
        await self._rebuild_bm25_for_shop("customer_service", shop_id)

    async def remove_custom_entry(self, entry_id: int, shop_id: int) -> None:
        self._vector_store.delete_by_filter("custom_knowledge", {
            "shop_id": shop_id, "source_id": entry_id,
        })
        await self._rebuild_bm25_for_shop("custom", shop_id)

    # ===== 查询 =====

    async def is_fresh(self, shop_id: int) -> bool:
        """检查店铺是否有向量索引"""
        for st in self._SOURCE_TYPES:
            col_name = self._collection_name(st)
            cnt = self._vector_store.count(col_name, {"shop_id": shop_id})
            if cnt > 0:
                return True
        # 也检查自定义知识
        cnt = self._vector_store.count("custom_knowledge", {"shop_id": shop_id})
        return cnt > 0

    @staticmethod
    def _collection_name(source_type: str) -> str:
        mapping = {
            "product": "product_knowledge",
            "customer_service": "customer_service_knowledge",
            "custom": "custom_knowledge",
        }
        return mapping.get(source_type, "custom_knowledge")
