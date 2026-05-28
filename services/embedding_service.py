"""
文本嵌入服务
支持 API 模式（OpenAI 兼容接口）和本地模型模式（sentence-transformers）。
API 模式默认复用 llm 配置的 api_key/api_base。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import List, Optional

from utils.logger_loguru import get_logger

logger = get_logger("EmbeddingService")


class EmbeddingService:
    """文本嵌入服务"""

    def __init__(self, config=None):
        """
        Args:
            config: KnowledgeBaseConfig 中的 embedding 子配置，或兼容的 dict/object
        """
        self._config = config
        self._provider = self._get_cfg("provider", "openai")
        self._model_name = self._get_cfg("model_name", "text-embedding-3-small")
        self._api_key = self._get_cfg("api_key", "")
        self._api_base = self._get_cfg("api_base", "")
        self._dimension = int(self._get_cfg("dimension", 1536))
        self._client = None
        self._local_model = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._lock = asyncio.Lock()

    def _get_cfg(self, key: str, default=None):
        if self._config is None:
            return default
        if hasattr(self._config, key):
            return getattr(self._config, key)
        if isinstance(self._config, dict):
            return self._config.get(key, default)
        return default

    def _get_client(self):
        """获取或创建 OpenAI 兼容客户端"""
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI

        api_key = self._api_key
        api_base = self._api_base

        # API 模式下，若未配置则回退到 llm 配置
        if self._provider == "openai" and (not api_key or not api_base):
            from config import get_config
            api_key = api_key or get_config("llm.api_key", "")
            api_base = api_base or get_config("llm.api_base", "")
        # 自动纠正：如果 api_key 填了 URL（常见错误），把它当 api_base
        if api_key and (api_key.startswith("http://") or api_key.startswith("https://")):
            logger.warning(f"检测到 api_key 看起来像 URL，已自动纠正: api_key 与 api_base 可能填反了")
            if not api_base or api_base == api_key:
                api_base = api_key
            from config import get_config
            api_key = get_config("llm.api_key", "")

        if not api_base:
            api_base = "https://api.openai.com/v1"

        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        logger.info(f"Embedding 客户端已初始化: base_url={api_base}, model={self._model_name}")
        return self._client

    def _get_local_model(self):
        """懒加载本地 sentence-transformers 模型"""
        if self._local_model is not None:
            return self._local_model
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载本地 Embedding 模型: {self._model_name}")
            self._local_model = SentenceTransformer(self._model_name)
            return self._local_model
        except ImportError:
            raise ImportError(
                "本地 Embedding 模式需要安装 sentence-transformers，"
                "请执行: pip install sentence-transformers"
            )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文本

        Args:
            texts: 待嵌入文本列表（建议单批不超过 32 条）

        Returns:
            嵌入向量列表，每个向量为 float 列表
        """
        if not texts:
            return []

        if self._provider == "local":
            return await self._embed_local(texts)
        else:
            return await self._embed_api(texts)

    async def embed_query(self, query: str) -> List[float]:
        """嵌入单条查询文本"""
        results = await self.embed([query])
        return results[0] if results else []

    async def _embed_api(self, texts: List[str]) -> List[List[float]]:
        """通过 API 嵌入"""
        client = self._get_client()
        logger.info(f"嵌入调用: texts={len(texts)}条, model={self._model_name}")
        try:
            # 分批处理
            all_embeddings = []
            batch_size = 32
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                resp = await client.embeddings.create(
                    model=self._model_name,
                    input=batch,
                )
                all_embeddings.extend([d.embedding for d in resp.data])
            return all_embeddings
        except Exception as e:
            logger.error(f"API 嵌入失败: {e}")
            raise

    async def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """通过本地模型嵌入（在线程池中运行以避免阻塞）"""
        model = self._get_local_model()
        loop = asyncio.get_running_loop()

        def _run():
            return model.encode(texts, normalize_embeddings=True).tolist()

        return await loop.run_in_executor(self._executor, _run)

    @property
    def dimension(self) -> int:
        return self._dimension
