"""
依赖注入容器 - 解决全局单例问题，提供更好的依赖管理
"""

from typing import Dict, Any, Callable, Type, Optional
from enum import Enum
import threading
import asyncio
from utils.logger_loguru import get_logger

class ServiceLifetime(Enum):
    """服务生命周期"""
    SINGLETON = "singleton"     # 单例
    TRANSIENT = "transient"     # 每次创建新实例
    SCOPED = "scoped"           # 作用域内单例

class ServiceDescriptor:
    """服务描述符"""
    def __init__(self,
                 service_type: Type,
                 implementation_type: Optional[Type] = None,
                 factory: Optional[Callable] = None,
                 instance: Optional[Any] = None,
                 lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT):
        self.service_type = service_type
        self.implementation_type = implementation_type
        self.factory = factory
        self.instance = instance
        self.lifetime = lifetime

class DIContainer:
    """依赖注入容器 - 支持多种服务生命周期"""

    def __init__(self):
        self._services: Dict[str, ServiceDescriptor] = {}
        self._singletons: Dict[str, Any] = {}
        self._scoped_instances: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self.logger = get_logger("DIContainer")

    def register_singleton(self, service_type: Type, instance: Any = None,
                         factory: Callable = None, implementation_type: Type = None):
        """注册单例服务"""
        if instance is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                instance=instance,
                lifetime=ServiceLifetime.SINGLETON
            )
        elif factory is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                lifetime=ServiceLifetime.SINGLETON
            )
        elif implementation_type is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation_type,
                lifetime=ServiceLifetime.SINGLETON
            )
        else:
            raise ValueError("必须提供 instance、factory 或 implementation_type 中的一个")

        with self._lock:
            key = service_type.__name__
            self._services[key] = descriptor
            self.logger.debug(f"注册单例服务: {key}")

        return self

    def register_transient(self, service_type: Type, implementation_type: Type = None,
                          factory: Callable = None):
        """注册瞬态服务（每次都创建新实例）"""
        if implementation_type is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation_type,
                lifetime=ServiceLifetime.TRANSIENT
            )
        elif factory is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                lifetime=ServiceLifetime.TRANSIENT
            )
        else:
            raise ValueError("必须提供 implementation_type 或 factory")

        with self._lock:
            key = service_type.__name__
            self._services[key] = descriptor
            self.logger.debug(f"注册瞬态服务: {key}")

        return self

    def register_scoped(self, service_type: Type, implementation_type: Type = None,
                       factory: Callable = None):
        """注册作用域服务（在同一个作用域内是单例）"""
        if implementation_type is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation_type,
                lifetime=ServiceLifetime.SCOPED
            )
        elif factory is not None:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                lifetime=ServiceLifetime.SCOPED
            )
        else:
            raise ValueError("必须提供 implementation_type 或 factory")

        with self._lock:
            key = service_type.__name__
            self._services[key] = descriptor
            self.logger.debug(f"注册作用域服务: {key}")

        return self

    def get(self, service_type: Type) -> Any:
        """获取服务实例"""
        key = service_type.__name__

        with self._lock:
            if key not in self._services:
                raise ValueError(f"服务 {service_type.__name__} 未注册")
            descriptor = self._services[key]

        # 处理单例（双重检查锁定，避免在锁内执行耗时创建）
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            if key in self._singletons:
                return self._singletons[key]

            with self._lock:
                if key in self._singletons:
                    return self._singletons[key]

                if descriptor.instance is not None:
                    instance = descriptor.instance
                elif descriptor.factory is not None:
                    instance = descriptor.factory()
                elif descriptor.implementation_type is not None:
                    instance = self._create_instance(descriptor.implementation_type)
                else:
                    raise ValueError(f"无法创建单例服务 {service_type.__name__}")

                self._singletons[key] = instance
                return instance

        # 处理作用域
        elif descriptor.lifetime == ServiceLifetime.SCOPED:
            if key in self._scoped_instances:
                return self._scoped_instances[key]

            with self._lock:
                if key in self._scoped_instances:
                    return self._scoped_instances[key]

                if descriptor.factory is not None:
                    instance = descriptor.factory()
                elif descriptor.implementation_type is not None:
                    instance = self._create_instance(descriptor.implementation_type)
                else:
                    raise ValueError(f"无法创建作用域服务 {service_type.__name__}")

                self._scoped_instances[key] = instance
                return instance

        # 处理瞬态
        elif descriptor.lifetime == ServiceLifetime.TRANSIENT:
            if descriptor.factory is not None:
                return descriptor.factory()
            elif descriptor.implementation_type is not None:
                return self._create_instance(descriptor.implementation_type)
            else:
                raise ValueError(f"无法创建瞬态服务 {service_type.__name__}")

    async def get_async(self, service_type: Type) -> Any:
        """异步获取服务实例"""
        key = service_type.__name__

        with self._lock:
            if key not in self._services:
                raise ValueError(f"服务 {service_type.__name__} 未注册")
            descriptor = self._services[key]

        # 处理单例（双重检查锁定，避免在锁内执行耗时创建）
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            if key in self._singletons:
                return self._singletons[key]

            with self._lock:
                if key in self._singletons:
                    return self._singletons[key]

                if descriptor.instance is not None:
                    instance = descriptor.instance
                elif descriptor.factory is not None and asyncio.iscoroutinefunction(descriptor.factory):
                    instance = await descriptor.factory()
                elif descriptor.factory is not None:
                    instance = descriptor.factory()
                elif descriptor.implementation_type is not None:
                    instance = await self._create_instance_async(descriptor.implementation_type)
                else:
                    raise ValueError(f"无法创建单例服务 {service_type.__name__}")

                self._singletons[key] = instance
                return instance

        # 处理作用域
        elif descriptor.lifetime == ServiceLifetime.SCOPED:
            if key in self._scoped_instances:
                return self._scoped_instances[key]

            with self._lock:
                if key in self._scoped_instances:
                    return self._scoped_instances[key]

                if descriptor.factory is not None and asyncio.iscoroutinefunction(descriptor.factory):
                    instance = await descriptor.factory()
                elif descriptor.factory is not None:
                    instance = descriptor.factory()
                elif descriptor.implementation_type is not None:
                    instance = await self._create_instance_async(descriptor.implementation_type)
                else:
                    raise ValueError(f"无法创建作用域服务 {service_type.__name__}")

                self._scoped_instances[key] = instance
                return instance

        # 处理瞬态
        elif descriptor.lifetime == ServiceLifetime.TRANSIENT:
            if descriptor.factory is not None and asyncio.iscoroutinefunction(descriptor.factory):
                return await descriptor.factory()
            elif descriptor.factory is not None:
                return descriptor.factory()
            elif descriptor.implementation_type is not None:
                return await self._create_instance_async(descriptor.implementation_type)
            else:
                raise ValueError(f"无法创建瞬态服务 {service_type.__name__}")

    def _create_instance(self, implementation_type: Type) -> Any:
        """创建实例（自动注入依赖）"""
        try:
            # 检查是否有构造函数参数需要注入
            import inspect
            signature = inspect.signature(implementation_type.__init__)

            if len(signature.parameters) <= 1:  # 只有self参数
                return implementation_type()

            # 需要依赖注入
            kwargs = {}
            for param_name, param in signature.parameters.items():
                if param_name == 'self':
                    continue

                if param.annotation != inspect.Parameter.empty:
                    dependency_type = param.annotation
                    kwargs[param_name] = self.get(dependency_type)

            return implementation_type(**kwargs)
        except Exception as e:
            self.logger.error(f"创建实例失败 {implementation_type.__name__}: {e}")
            raise RuntimeError(f"Failed to create instance of {implementation_type.__name__}") from e

    async def _create_instance_async(self, implementation_type: Type) -> Any:
        """异步创建实例（自动注入依赖）"""
        try:
            # 检查是否有构造函数参数需要注入
            import inspect
            signature = inspect.signature(implementation_type.__init__)

            if len(signature.parameters) <= 1:  # 只有self参数
                return implementation_type()

            # 需要依赖注入
            kwargs = {}
            for param_name, param in signature.parameters.items():
                if param_name == 'self':
                    continue

                if param.annotation != inspect.Parameter.empty:
                    dependency_type = param.annotation
                    kwargs[param_name] = await self.get_async(dependency_type)

            return implementation_type(**kwargs)
        except Exception as e:
            self.logger.error(f"异步创建实例失败 {implementation_type.__name__}: {e}")
            raise

    def clear_scoped(self):
        """清除作用域实例"""
        with self._lock:
            self._scoped_instances.clear()
            self.logger.debug("已清除所有作用域实例")

    def is_registered(self, service_type: Type) -> bool:
        """检查服务是否已注册"""
        key = service_type.__name__
        return key in self._services

    def get_registered_services(self) -> Dict[str, str]:
        """获取已注册的服务列表"""
        with self._lock:
            return {
                key: f"{descriptor.service_type.__name__} ({descriptor.lifetime.value})"
                for key, descriptor in self._services.items()
            }

    def dispose(self):
        """释放容器资源"""
        with self._lock:
            # 调用单例实例的dispose方法（如果有）
            for instance in self._singletons.values():
                if hasattr(instance, 'dispose') and callable(getattr(instance, 'dispose')):
                    try:
                        instance.dispose()
                    except Exception as e:
                        self.logger.error(f"释放实例失败: {e}")

            # 清除所有实例
            self._singletons.clear()
            self._scoped_instances.clear()
            self.logger.info("依赖注入容器已释放")


# 全局容器实例
container = DIContainer()


def _register_knowledge_base_services(container: 'DIContainer', config_instance: Any = None):
    """注册向量知识库相关服务（按依赖顺序）"""
    from services.chunking_service import ChunkingService
    from services.embedding_service import EmbeddingService
    from services.vector_store import VectorStore
    from services.bm25_index import BM25Index
    from services.hybrid_retriever import HybridRetriever
    from services.reranker_service import RerankerService
    from services.vector_index_sync import VectorIndexSync
    from services.custom_knowledge_service import CustomKnowledgeService
    from database.knowledge_service import KnowledgeService

    # 从 config 读取配置
    kb_config = None
    if config_instance is not None:
        try:
            kb_config = config_instance.get("knowledge_base", {})
        except Exception:
            kb_config = {}
    if not kb_config:
        from config import get_config
        kb_config = get_config("knowledge_base", {})

    # 1. ChunkingService
    chunk_size = kb_config.get("chunk_size", 500) if isinstance(kb_config, dict) else getattr(kb_config, "chunk_size", 500)
    chunk_overlap = kb_config.get("chunk_overlap", 50) if isinstance(kb_config, dict) else getattr(kb_config, "chunk_overlap", 50)
    if not container.is_registered(ChunkingService):
        container.register_singleton(
            ChunkingService,
            factory=lambda cs=chunk_size, co=chunk_overlap: ChunkingService(chunk_size=cs, chunk_overlap=co),
        )

    # 2. EmbeddingService
    emb_cfg = kb_config.get("embedding", {}) if isinstance(kb_config, dict) else getattr(kb_config, "embedding", None)
    if not container.is_registered(EmbeddingService):
        container.register_singleton(
            EmbeddingService,
            factory=lambda cfg=emb_cfg: EmbeddingService(config=cfg),
        )

    # 3. VectorStore
    vb_cfg = kb_config.get("vector_db", {}) if isinstance(kb_config, dict) else getattr(kb_config, "vector_db", None)
    persist_dir = vb_cfg.get("persist_directory", "./temp/vector_db") if isinstance(vb_cfg, dict) else (getattr(vb_cfg, "persist_directory", "./temp/vector_db") if vb_cfg else "./temp/vector_db")
    if not container.is_registered(VectorStore):
        container.register_singleton(
            VectorStore,
            factory=lambda pd=persist_dir: VectorStore(persist_directory=pd),
        )

    # 4. BM25Index
    if not container.is_registered(BM25Index):
        container.register_singleton(BM25Index, factory=lambda: BM25Index())

    # 5. HybridRetriever
    if not container.is_registered(HybridRetriever):
        container.register_singleton(
            HybridRetriever,
            factory=lambda: HybridRetriever(
                vector_store=container.get(VectorStore),
                bm25_index=container.get(BM25Index),
                embedding_service=container.get(EmbeddingService),
            ),
        )

    # 6. RerankerService
    rerank_cfg = kb_config.get("reranker", {}) if isinstance(kb_config, dict) else getattr(kb_config, "reranker", None)
    if not container.is_registered(RerankerService):
        container.register_singleton(
            RerankerService,
            factory=lambda cfg=rerank_cfg: RerankerService(config=cfg),
        )

    # 7. VectorIndexSync
    if not container.is_registered(VectorIndexSync):
        container.register_singleton(
            VectorIndexSync,
            factory=lambda: VectorIndexSync(
                vector_store=container.get(VectorStore),
                bm25_index=container.get(BM25Index),
                embedding_service=container.get(EmbeddingService),
                chunking_service=container.get(ChunkingService),
            ),
        )

    # 8. CustomKnowledgeService
    if not container.is_registered(CustomKnowledgeService):
        container.register_singleton(
            CustomKnowledgeService,
            factory=lambda: CustomKnowledgeService(
                vector_sync=container.get(VectorIndexSync),
                chunking_service=container.get(ChunkingService),
            ),
        )

    # 9. 重新注入 KnowledgeService（升级构造函数）
    _upgrade_knowledge_service(container)


def _upgrade_knowledge_service(container: 'DIContainer'):
    """注入混合检索等新服务到 KnowledgeService"""
    from database.knowledge_service import KnowledgeService
    from services.hybrid_retriever import HybridRetriever
    from services.reranker_service import RerankerService
    from services.vector_index_sync import VectorIndexSync

    from database.knowledge_service import logger as ks_logger
    ks = container.get(KnowledgeService)
    try:
        ks.hybrid_retriever = container.get(HybridRetriever)
    except Exception as e:
        ks_logger.warning(f"HybridRetriever 注入失败: {e}")
    try:
        ks.reranker_service = container.get(RerankerService)
    except Exception as e:
        ks_logger.warning(f"RerankerService 注入失败: {e}")
    try:
        ks.vector_index_sync = container.get(VectorIndexSync)
        ks.vector_index_sync.set_knowledge_service(ks)
    except Exception as e:
        ks_logger.warning(f"VectorIndexSync 注入失败: {e}")

    # 注入后重新诊断
    if ks.hybrid_retriever and ks.reranker_service:
        ks_logger.info("KnowledgeService 已就绪 [模式: 混合检索(向量+BM25+RRF) + 重排序]")
    elif ks.hybrid_retriever:
        ks_logger.info("KnowledgeService 已就绪 [模式: 混合检索(向量+BM25+RRF), 无重排序]")
    else:
        ks_logger.warning("KnowledgeService 运行在传统检索模式(jieba+SQL LIKE)，向量检索不可用")


def configure_standard_services(config_instance: Any = None) -> 'DIContainer':
    """
    按依赖顺序注册核心标准服务到 DI 容器

    目前仅注册需要 DI 统一管理的服务：
    1. ConnectionStatusManager — 连接状态管理（跨 PDDChannel 实例共享）
    2. DatabaseManager — 数据库管理器

    其他服务（QueueManager、MessageConsumerManager、CacheManager）
    已通过模块级单例直接使用，无需重复注册。

    必须在其他模块导入前调用（通常在 app.py 中），
    以确保服务在需要时可从容器获取。
    """
    # 提前导入，避免 Python 局部变量作用域问题
    from core.connection_status import ConnectionStatusManager
    from database.db_manager import DatabaseManager

    # 1. ConnectionStatusManager（最独立，先注册）
    if not container.is_registered(ConnectionStatusManager):
        container.register_singleton(
            ConnectionStatusManager,
            factory=lambda: ConnectionStatusManager()
        )

    # 2. DatabaseManager
    if not container.is_registered(DatabaseManager):
        db_path = "./temp/channel_shop.db"
        if config_instance is not None:
            db_path = config_instance.get("db_path", db_path)
        container.register_singleton(
            DatabaseManager,
            factory=lambda: DatabaseManager(db_path=db_path)
        )

    # 3. KnowledgeService（知识库服务）
    from database.knowledge_service import KnowledgeService
    if not container.is_registered(KnowledgeService):
        container.register_singleton(
            KnowledgeService,
            factory=lambda: KnowledgeService()
        )

    # 4. 向量知识库相关服务（按依赖顺序注册）
    _register_knowledge_base_services(container, config_instance)

    # 注：QueueManager、MessageConsumerManager、CacheManager
    # 已在各自模块中定义了模块级单例实例（如 Message/core/queue.py 中的 queue_manager），
    # 代码中通过 `from Message import queue_manager` 直接使用，无需重复注册到 DI 容器，
    # 保持 DI 容器仅管理需要跨模块共享的服务（如 ConnectionStatusManager）。

    container.logger.info(
        f"标准服务配置完成，已注册: {list(container.get_registered_services().keys())}"
    )
    return container

# 便捷装饰器
def injectable(service_type: Type = None, lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT):
    """可注入装饰器"""
    def decorator(cls):
        nonlocal service_type
        if service_type is None:
            service_type = cls

        if lifetime == ServiceLifetime.SINGLETON:
            container.register_singleton(service_type, implementation_type=cls)
        elif lifetime == ServiceLifetime.TRANSIENT:
            container.register_transient(service_type, implementation_type=cls)
        elif lifetime == ServiceLifetime.SCOPED:
            container.register_scoped(service_type, implementation_type=cls)

        return cls
    return decorator