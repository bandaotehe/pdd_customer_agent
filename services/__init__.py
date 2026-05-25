"""
Services 包 — 知识库升级核心服务

提供：
- ChunkingService: 文本智能分块
- EmbeddingService: 文本嵌入（API + 本地模型）
- VectorStore: Chroma 向量库 CRUD + 检索
- BM25Index: 关键词 BM25 索引
- HybridRetriever: 混合检索 + RRF 融合
- RerankerService: Cross-Encoder 重排序
- VectorIndexSync: 向量索引同步/迁移
- CustomKnowledgeService: 自定义知识 CRUD
"""

from services.chunking_service import ChunkingService
from services.embedding_service import EmbeddingService
from services.vector_store import VectorStore
from services.bm25_index import BM25Index
from services.hybrid_retriever import HybridRetriever
from services.reranker_service import RerankerService
from services.vector_index_sync import VectorIndexSync, SyncProgress
from services.custom_knowledge_service import CustomKnowledgeService

__all__ = [
    "ChunkingService",
    "EmbeddingService",
    "VectorStore",
    "BM25Index",
    "HybridRetriever",
    "RerankerService",
    "VectorIndexSync",
    "SyncProgress",
    "CustomKnowledgeService",
]
