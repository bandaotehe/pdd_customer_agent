"""
BM25 关键词索引服务
按 {source_type}:{shop_id} 分组构建 BM25Okapi 索引，支持 jieba 分词检索。
"""
from __future__ import annotations

from typing import List, Dict
import jieba
from rank_bm25 import BM25Okapi
from utils.logger_loguru import get_logger

logger = get_logger("BM25Index")


class BM25Index:
    """BM25 关键词索引（内存缓存）"""

    def __init__(self):
        # key: "{source_type}:{shop_id}" -> BM25Okapi
        self._indices: Dict[str, BM25Okapi] = {}
        # key: "{source_type}:{shop_id}" -> List[metadata dict]
        self._metadatas: Dict[str, List[Dict]] = {}

    def _key(self, source_type: str, shop_id: int) -> str:
        return f"{source_type}:{shop_id}"

    def _tokenize(self, text: str) -> List[str]:
        """jieba 分词"""
        return list(jieba.cut_for_search(text or ""))

    def build_index(
        self,
        source_type: str,
        shop_id: int,
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        """为指定 source_type + shop_id 构建 BM25 索引"""
        key = self._key(source_type, shop_id)
        tokenized = [self._tokenize(doc) for doc in documents]
        self._indices[key] = BM25Okapi(tokenized)
        self._metadatas[key] = metadatas
        logger.debug(f"BM25 索引已构建: {key}, documents={len(documents)}")

    def search(
        self,
        source_type: str,
        shop_id: int,
        query: str,
        top_k: int = 20,
    ) -> List[Dict]:
        """检索并返回 top_k 结果

        Returns:
            [{id, metadata, document, bm25_score}, ...]
        """
        key = self._key(source_type, shop_id)
        if key not in self._indices:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._indices[key].get_scores(tokenized_query)
        metadatas = self._metadatas[key]

        # 取 top_k
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        top = indexed[:top_k]

        results = []
        for idx, score in top:
            if score > 0:
                meta = metadatas[idx] if idx < len(metadatas) else {}
                results.append({
                    "id": meta.get("id", ""),
                    "metadata": meta,
                    "document": meta.get("text", ""),
                    "bm25_score": float(score),
                })
        return results

    def delete_index(self, source_type: str, shop_id: int) -> None:
        """删除缓存索引"""
        key = self._key(source_type, shop_id)
        self._indices.pop(key, None)
        self._metadatas.pop(key, None)
        logger.debug(f"BM25 索引已删除: {key}")

    def has_index(self, source_type: str, shop_id: int) -> bool:
        key = self._key(source_type, shop_id)
        return key in self._indices and len(self._indices[key].doc_len) > 0
