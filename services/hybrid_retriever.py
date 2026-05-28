"""
混合检索器
向量语义检索 + BM25 关键词检索，通过 RRF (Reciprocal Rank Fusion) 融合排序。
"""
from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Optional

from services.vector_store import VectorStore, ALL_COLLECTIONS
from services.bm25_index import BM25Index
from services.embedding_service import EmbeddingService
from utils.logger_loguru import get_logger

logger = get_logger("HybridRetriever")

RRF_K = 60  # RRF 平滑常数


class HybridRetriever:
    """混合检索器：向量 + BM25 → RRF 融合"""

    _SOURCE_TYPE_MAP = {
        "product": "product_knowledge",
        "customer_service": "customer_service_knowledge",
        "custom": "custom_knowledge",
    }

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        embedding_service: EmbeddingService,
    ):
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._embedding = embedding_service

    async def search(
        self,
        query: str,
        shop_id: int,
        source_types: Optional[List[str]] = None,
        top_k_per_source: int = 30,
        alpha: float = 0.5,
    ) -> List[Dict]:
        """混合检索

        Args:
            query: 查询文本
            shop_id: 店铺 ID
            source_types: 来源类型列表，默认全部 ['product', 'customer_service', 'custom']
            top_k_per_source: 每种来源的检索数量
            alpha: 融合权重，1=纯向量，0=纯BM25

        Returns:
            [{source_type, source_id, chunk_index, text, vector_score, bm25_score, final_score}, ...]
        """
        if source_types is None:
            source_types = ["product", "customer_service", "custom"]

        t0 = time.perf_counter()

        # 1. 向量嵌入查询
        query_embedding = await self._embedding.embed_query(query)
        embed_ms = (time.perf_counter() - t0) * 1000
        if not query_embedding:
            logger.warning("查询嵌入失败，降级为纯 BM25")
            alpha = 0.0
        else:
            logger.info(f"嵌入完成: query={query[:30]}, dim={len(query_embedding)}, 耗时={embed_ms:.0f}ms")

        # 2. 并行检索
        tasks = []
        for st in source_types:
            tasks.append(self._search_single(st, shop_id, query, query_embedding, top_k_per_source, alpha))

        all_results = await asyncio.gather(*tasks)
        search_ms = (time.perf_counter() - t0) * 1000

        # 3. 合并 + RRF 融合
        merged = []
        for results in all_results:
            merged.extend(results)

        # 按 final_score 降序排序
        merged.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        logger.info(f"混合检索完成: query={query[:30]}, 候选={len(merged)}条, 总耗时={search_ms:.0f}ms")
        if merged:
            top = merged[0]
            logger.info(f"  Top1: type={top.get('source_type')} score={top.get('final_score',0):.4f} text={top.get('text','')[:60]}")
        return merged

    async def _search_single(
        self,
        source_type: str,
        shop_id: int,
        query: str,
        query_embedding: List[float],
        top_k: int,
        alpha: float,
    ) -> List[Dict]:
        """对单个 source_type 执行混合检索"""
        col_name = self._SOURCE_TYPE_MAP[source_type]
        where = {"shop_id": shop_id}

        # 向量检索
        vector_results = []
        if query_embedding and alpha > 0:
            vector_results = self._vector_store.search(col_name, query_embedding, top_k, where)

        # BM25 检索
        bm25_results = []
        if alpha < 1.0:
            bm25_results = self._bm25.search(source_type, shop_id, query, top_k)

        # RRF 融合
        return self._rrf_fusion(vector_results, bm25_results, alpha, source_type)

    def _rrf_fusion(
        self,
        vector_results: List[Dict],
        bm25_results: List[Dict],
        alpha: float,
        source_type: str,
    ) -> List[Dict]:
        """Reciprocal Rank Fusion"""
        # 构建 doc_id -> {vector_rank, bm25_rank, metadata, document}
        doc_map: Dict[str, Dict] = {}

        for rank, item in enumerate(vector_results):
            doc_id = item["id"]
            doc_map[doc_id] = {
                "vector_rank": rank + 1,
                "bm25_rank": float("inf"),
                "vector_score": 1.0 / (RRF_K + rank + 1),
                "bm25_score": 0.0,
                "metadata": item.get("metadata", {}),
                "document": item.get("document", ""),
            }

        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            if doc_id in doc_map:
                doc_map[doc_id]["bm25_rank"] = rank + 1
                doc_map[doc_id]["bm25_score"] = 1.0 / (RRF_K + rank + 1)
            else:
                doc_map[doc_id] = {
                    "vector_rank": float("inf"),
                    "bm25_rank": rank + 1,
                    "vector_score": 0.0,
                    "bm25_score": 1.0 / (RRF_K + rank + 1),
                    "metadata": item.get("metadata", {}),
                    "document": item.get("document", ""),
                }

        # 归一化
        vec_scores = [v["vector_score"] for v in doc_map.values() if v["vector_score"] > 0]
        bm25_scores = [v["bm25_score"] for v in doc_map.values() if v["bm25_score"] > 0]

        vec_max = max(vec_scores) if vec_scores else 1.0
        bm25_max = max(bm25_scores) if bm25_scores else 1.0

        results = []
        for doc_id, info in doc_map.items():
            norm_vec = info["vector_score"] / vec_max if vec_max > 0 else 0
            norm_bm25 = info["bm25_score"] / bm25_max if bm25_max > 0 else 0
            final_score = alpha * norm_vec + (1 - alpha) * norm_bm25

            meta = info["metadata"]
            results.append({
                "id": doc_id,
                "source_type": source_type,
                "source_id": meta.get("source_id"),
                "chunk_index": meta.get("chunk_index"),
                "text": info["document"],
                "metadata": meta,
                "vector_score": round(info["vector_score"], 6),
                "bm25_score": round(info["bm25_score"], 6),
                "final_score": round(final_score, 6),
            })

        return results
