"""
重排序服务
对候选结果进行 Cross-Encoder 精排，选出最相关的 Top-K。
支持本地模型和 API 两种模式。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import List, Dict, Optional

from utils.logger_loguru import get_logger

logger = get_logger("RerankerService")


class RerankerService:
    """Cross-Encoder 重排序服务"""

    def __init__(self, config=None):
        """
        Args:
            config: KnowledgeBaseConfig 中的 reranker 子配置
        """
        self._config = config
        self._provider = self._get_cfg("provider", "local")
        self._model_name = self._get_cfg("model_name", "BAAI/bge-reranker-v2-m3")
        self._api_key = self._get_cfg("api_key", "")
        self._api_base = self._get_cfg("api_base", "")
        self._model = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _get_cfg(self, key: str, default=None):
        if self._config is None:
            return default
        if hasattr(self._config, key):
            return getattr(self._config, key)
        if isinstance(self._config, dict):
            return self._config.get(key, default)
        return default

    def _get_model(self):
        """懒加载 Cross-Encoder 模型"""
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"加载 Cross-Encoder 模型: {self._model_name}")
            self._model = CrossEncoder(self._model_name, max_length=512)
            return self._model
        except ImportError:
            raise ImportError(
                "本地 Reranker 模式需要安装 sentence-transformers，"
                "请执行: pip install sentence-transformers"
            )

    async def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int = 10,
    ) -> List[Dict]:
        """重排序候选结果

        Args:
            query: 查询文本
            candidates: 候选列表，每项至少含 'text' 字段
            top_k: 返回数量

        Returns:
            排序后的候选列表，每项追加 'rerank_score' 字段
        """
        if not candidates:
            return []

        if len(candidates) <= top_k:
            # 无需精排，直接标记
            for c in candidates:
                c["rerank_score"] = 1.0
            return candidates

        if self._provider == "api":
            return await self._rerank_api(query, candidates, top_k)
        else:
            return await self._rerank_local(query, candidates, top_k)

    async def _rerank_local(
        self, query: str, candidates: List[Dict], top_k: int
    ) -> List[Dict]:
        """本地 Cross-Encoder 重排序"""
        model = self._get_model()
        loop = asyncio.get_running_loop()

        # 准备 (query, doc) 对，截断过长文本
        pairs = []
        for c in candidates:
            text = c.get("text", "")
            if len(text) > 500:
                text = text[:500]
            pairs.append([query, text])

        def _run():
            return model.predict(pairs).tolist()

        scores = await loop.run_in_executor(self._executor, _run)

        for i, c in enumerate(candidates):
            c["rerank_score"] = round(float(scores[i]), 6) if i < len(scores) else 0.0

        candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return candidates[:top_k]

    async def _rerank_api(
        self, query: str, candidates: List[Dict], top_k: int
    ) -> List[Dict]:
        """API 方式重排序（Cohere 兼容 / OpenAI 兼容）"""
        import aiohttp

        if not self._api_base:
            logger.warning("Reranker API base 未配置，返回原始顺序")
            for c in candidates:
                c["rerank_score"] = 1.0
            return candidates[:top_k]

        documents = [c.get("text", "")[:500] for c in candidates]

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self._model_name,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                }
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self._api_base.rstrip('/')}/rerank",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        # 重建排序列表
                        reranked = []
                        for r in results:
                            idx = r.get("index", 0)
                            if idx < len(candidates):
                                c = candidates[idx]
                                c["rerank_score"] = round(float(r.get("relevance_score", 0)), 6)
                                reranked.append(c)
                        return reranked[:top_k]
                    else:
                        logger.error(f"Reranker API 调用失败: {resp.status}")
                        # 降级：返回原始顺序
                        for c in candidates:
                            c["rerank_score"] = 1.0
                        return candidates[:top_k]
        except Exception as e:
            logger.error(f"Reranker API 调用异常: {e}")
            for c in candidates:
                c["rerank_score"] = 1.0
            return candidates[:top_k]
