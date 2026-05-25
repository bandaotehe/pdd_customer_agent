"""
Chroma 向量库服务
管理 3 个 Collection：product_knowledge / customer_service_knowledge / custom_knowledge
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional

import chromadb
from chromadb.config import Settings

from utils.logger_loguru import get_logger

logger = get_logger("VectorStore")

COLLECTION_PRODUCT = "product_knowledge"
COLLECTION_CS = "customer_service_knowledge"
COLLECTION_CUSTOM = "custom_knowledge"

ALL_COLLECTIONS = [COLLECTION_PRODUCT, COLLECTION_CS, COLLECTION_CUSTOM]


class VectorStore:
    """Chroma 向量库服务"""

    def __init__(self, persist_directory: str = "./temp/vector_db"):
        self._persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )
        # 预创建 collection（幂等）
        for name in ALL_COLLECTIONS:
            self._get_or_create_collection(name)
        logger.info(f"VectorStore 初始化完成: path={persist_directory}")

    def _get_or_create_collection(self, name: str):
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def _collection(self, name: str):
        return self._client.get_collection(name)

    @staticmethod
    def _normalize_where(where_filter: Optional[Dict]) -> Optional[Dict]:
        """ChromaDB 1.x 要求多条件时使用 $and 语法"""
        if where_filter and len(where_filter) > 1:
            return {"$and": [{k: v} for k, v in where_filter.items()]}
        return where_filter

    # ===== 写入 =====

    def add_documents(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        documents: List[str],
    ) -> None:
        """批量添加文档到指定 collection"""
        if not ids:
            return
        col = self._collection(collection_name)
        col.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        logger.debug(f"添加 {len(ids)} 条文档到 {collection_name}")

    # ===== 检索 =====

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 20,
        where_filter: Optional[Dict] = None,
    ) -> List[Dict]:
        """向量语义检索

        Returns:
            [{id, metadata, document, distance}, ...]
        """
        col = self._collection(collection_name)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=self._normalize_where(where_filter),
            include=["documents", "metadatas", "distances"],
        )
        # 展平结果
        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "id": doc_id,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })
        return output

    # ===== 删除 =====

    def delete_by_filter(self, collection_name: str, where_filter: Dict) -> None:
        """按条件删除"""
        col = self._collection(collection_name)
        col.delete(where=self._normalize_where(where_filter))
        logger.debug(f"删除 {collection_name} 中匹配 {where_filter} 的条目")

    def delete_by_shop(self, collection_name: str, shop_id: int) -> None:
        """删除某店铺在指定 collection 中的所有条目"""
        self.delete_by_filter(collection_name, {"shop_id": shop_id})

    def delete_by_shop_all(self, shop_id: int) -> None:
        """删除某店铺在所有 collection 中的条目"""
        for name in ALL_COLLECTIONS:
            self.delete_by_shop(name, shop_id)

    # ===== 统计 =====

    def count(self, collection_name: str, where_filter: Optional[Dict] = None) -> int:
        """计数"""
        col = self._collection(collection_name)
        if where_filter:
            result = col.get(where=self._normalize_where(where_filter), include=[])
            return len(result["ids"]) if result["ids"] else 0
        return col.count()
