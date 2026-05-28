"""
知识库服务
=============

提供知识库的CRUD操作和检索功能。
支持传统 jieba LIKE 检索和升级后的混合向量检索（可选）。
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
import jieba
import queue
import threading
from utils.logger_loguru import get_logger
from database.models import Base, ProductKnowledge, CustomerServiceKnowledge, CustomKnowledge, Shop
from database.db_manager import db_manager

if TYPE_CHECKING:
    from services.hybrid_retriever import HybridRetriever
    from services.reranker_service import RerankerService
    from services.vector_index_sync import VectorIndexSync

logger = get_logger("KnowledgeService")


class KnowledgeService:
    """知识库服务，提供产品知识和客服知识的CRUD和检索功能"""

    def __init__(
        self,
        hybrid_retriever: Optional["HybridRetriever"] = None,
        reranker_service: Optional["RerankerService"] = None,
        vector_index_sync: Optional["VectorIndexSync"] = None,
    ):
        """初始化知识库服务

        Args:
            hybrid_retriever: 混合检索器（可选，未提供时降级为传统 LIKE 检索）
            reranker_service: 重排序服务（可选）
            vector_index_sync: 向量索引同步服务（可选）
        """
        self.session_factory = db_manager.Session
        Base.metadata.create_all(db_manager.engine)
        self.hybrid_retriever = hybrid_retriever
        self.reranker_service = reranker_service
        self.vector_index_sync = vector_index_sync

        # 启动诊断
        if hybrid_retriever and reranker_service:
            logger.info("KnowledgeService 已就绪 [模式: 混合检索(向量+BM25+RRF) + 重排序]")
        elif hybrid_retriever:
            logger.info("KnowledgeService 已就绪 [模式: 混合检索(向量+BM25+RRF), 无重排序]")
        else:
            logger.info("KnowledgeService 已就绪 [模式: 传统检索(jieba+SQL LIKE), 向量检索不可用]")

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.session_factory()

    def _schedule_async(self, coro):
        """将异步索引任务提交到单一线程执行，避免每个商品开一个线程"""
        if self.vector_index_sync is None:
            return
        self._ensure_index_worker()
        self._index_queue.put(coro)

    def _ensure_index_worker(self):
        """确保索引工作线程已启动（单例，所有索引任务共用）"""
        if hasattr(self, '_index_thread') and self._index_thread is not None and self._index_thread.is_alive():
            return
        self._index_queue = queue.Queue()
        self._index_thread = threading.Thread(target=self._index_worker, daemon=True)
        self._index_thread.start()
        logger.info("向量索引工作线程已启动")

    def _index_worker(self):
        """单一线程按序处理所有异步索引任务"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            try:
                coro = self._index_queue.get(timeout=5)
                loop.run_until_complete(coro)
            except queue.Empty:
                continue
            except Exception as e:
                msg = str(e)
                if "dimension" in msg.lower() or "expecting" in msg.lower():
                    logger.error(
                        f"向量索引维度不匹配，请删除向量库后重新同步。\n"
                        f"  1. 关闭程序\n"
                        f"  2. 删除 temp/vector_db 目录\n"
                        f"  3. 检查 config.json 中 knowledge_base.embedding.dimension 与实际模型输出一致\n"
                        f"  4. 重启程序并重新同步产品知识\n"
                        f"  原始错误: {msg}"
                    )
                else:
                    logger.error(f"向量索引后台任务失败: {msg}")

    def _reindex_product(self, product):
        if not product:
            return
        if not self.vector_index_sync:
            logger.warning(f"vector_index_sync 未注入，跳过向量索引: goods_id={product.goods_id}")
            return
        text = product.goods_name or ""
        if product.extracted_content:
            text = f"{text}\n{product.extracted_content}"
        logger.info(f"入向量库: goods_id={product.goods_id}, len={len(text)}")
        self._schedule_async(
            self.vector_index_sync.index_raw(
                "product", product.id, product.shop_id,
                text,
                goods_id=product.goods_id,
            )
        )

    def _reindex_cs(self, cs):
        if cs and cs.content and self.vector_index_sync:
            self._schedule_async(
                self.vector_index_sync.index_raw(
                    "customer_service", cs.id, cs.shop_id,
                    f"{cs.title}\n{cs.content}",
                )
            )

    def _remove_vector(self, coro):
        if self.vector_index_sync:
            self._schedule_async(coro)

    # ========== 产品知识 ==========

    def get_product_by_goods_id(self, shop_id: int, goods_id: int) -> Optional[ProductKnowledge]:
        """根据商品ID获取产品知识"""
        with self.get_session() as session:
            stmt = select(ProductKnowledge).where(
                and_(
                    ProductKnowledge.shop_id == shop_id,
                    ProductKnowledge.goods_id == goods_id
                )
            )
            return session.scalar(stmt)

    def list_products_by_shop(self, shop_id: int) -> List[ProductKnowledge]:
        """获取店铺所有产品知识"""
        with self.get_session() as session:
            stmt = select(ProductKnowledge).where(
                ProductKnowledge.shop_id == shop_id
            ).order_by(ProductKnowledge.created_at.desc())
            return list(session.scalars(stmt))

    def count_products_by_shop(self, shop_id: int) -> int:
        """统计店铺产品知识数量"""
        with self.get_session() as session:
            return session.query(ProductKnowledge).filter(
                ProductKnowledge.shop_id == shop_id
            ).count()

    def add_or_update_product(
        self,
        shop_id: int,
        goods_id: int,
        goods_name: str,
        price: Optional[str] = None,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None,
        sold_quantity: Optional[int] = None,
        thumb_url: Optional[str] = None,
        specifications: Optional[str] = None,
        extracted_content: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> ProductKnowledge:
        """添加或更新产品知识"""
        with self.get_session() as session:
            # 在同一个 session 中查询
            stmt = select(ProductKnowledge).where(
                and_(
                    ProductKnowledge.shop_id == shop_id,
                    ProductKnowledge.goods_id == goods_id
                )
            )
            existing = session.scalar(stmt)

            if existing:
                # 更新现有记录
                if goods_name is not None:
                    existing.goods_name = goods_name
                if price is not None:
                    existing.price = price
                if price_min is not None:
                    existing.price_min = price_min
                if price_max is not None:
                    existing.price_max = price_max
                if sold_quantity is not None:
                    existing.sold_quantity = sold_quantity
                if thumb_url is not None:
                    existing.thumb_url = thumb_url
                if specifications is not None:
                    existing.specifications = specifications
                if extracted_content is not None:
                    existing.extracted_content = extracted_content
                if image_path is not None:
                    existing.image_path = image_path
                existing.last_extracted_at = datetime.now()
                product = existing
                session.flush()
            else:
                # 创建新记录
                product = ProductKnowledge(
                    shop_id=shop_id,
                    goods_id=goods_id,
                    goods_name=goods_name,
                    price=price,
                    price_min=price_min,
                    price_max=price_max,
                    sold_quantity=sold_quantity,
                    thumb_url=thumb_url,
                    specifications=specifications,
                    extracted_content=extracted_content,
                    image_path=image_path,
                )
                session.add(product)
                session.flush()

            session.commit()
            # 重新查询以确保返回的是附加到 session 的对象
            stmt = select(ProductKnowledge).where(
                and_(
                    ProductKnowledge.shop_id == shop_id,
                    ProductKnowledge.goods_id == goods_id
                )
            )
            result = session.scalar(stmt)
            logger.info(f"产品知识保存成功: shop_id={shop_id}, goods_id={goods_id}")
            self._reindex_product(result)
            return result

    def update_product_extracted_content(
        self,
        shop_id: int,
        goods_id: int,
        specifications: Optional[str] = None,
        extracted_content: Optional[str] = None,
    ) -> bool:
        """仅更新产品的提取内容（用于第二阶段更新）"""
        with self.get_session() as session:
            stmt = select(ProductKnowledge).where(
                and_(
                    ProductKnowledge.shop_id == shop_id,
                    ProductKnowledge.goods_id == goods_id
                )
            )
            product = session.scalar(stmt)
            if not product:
                logger.warning(f"产品不存在，无法更新提取内容: shop_id={shop_id}, goods_id={goods_id}")
                return False

            if specifications is not None:
                product.specifications = specifications
            if extracted_content is not None:
                product.extracted_content = extracted_content
            product.last_extracted_at = datetime.now()

            session.commit()
            logger.info(f"产品提取内容更新成功: shop_id={shop_id}, goods_id={goods_id}")
            self._reindex_product(product)
            return True

    def delete_product(self, product_id: int) -> bool:
        """删除产品知识"""
        with self.get_session() as session:
            product = session.get(ProductKnowledge, product_id)
            if not product:
                return False
            shop_id = product.shop_id
            session.delete(product)
            session.commit()
            logger.info(f"产品知识删除成功: id={product_id}")
            self._remove_vector(self.vector_index_sync.remove_product(product_id, shop_id))
            return True

    def clear_products_by_shop(self, shop_id: int) -> int:
        """清空店铺所有产品知识，返回删除数量"""
        with self.get_session() as session:
            count = session.query(ProductKnowledge).filter(
                ProductKnowledge.shop_id == shop_id
            ).delete()
            session.commit()
            logger.info(f"清空店铺产品知识: shop_id={shop_id}, deleted={count}")
            return count

    # ========== 客服知识 ==========

    def get_customer_service_by_id(self, cs_id: int) -> Optional[CustomerServiceKnowledge]:
        """根据ID获取客服知识"""
        with self.get_session() as session:
            return session.get(CustomerServiceKnowledge, cs_id)

    def list_customer_service_by_shop(self, shop_id: int) -> List[CustomerServiceKnowledge]:
        """获取店铺所有启用的客服知识"""
        with self.get_session() as session:
            stmt = select(CustomerServiceKnowledge).where(
                and_(
                    CustomerServiceKnowledge.shop_id == shop_id,
                    CustomerServiceKnowledge.enabled == True
                )
            ).order_by(CustomerServiceKnowledge.created_at.desc())
            return list(session.scalars(stmt))

    def list_customer_service_with_disabled(self, shop_id: int) -> List[CustomerServiceKnowledge]:
        """获取店铺所有客服知识（包括禁用的）"""
        with self.get_session() as session:
            stmt = select(CustomerServiceKnowledge).where(
                CustomerServiceKnowledge.shop_id == shop_id
            ).order_by(CustomerServiceKnowledge.created_at.desc())
            return list(session.scalars(stmt))

    def count_customer_service_by_shop(self, shop_id: int) -> int:
        """统计店铺客服知识数量"""
        with self.get_session() as session:
            return session.query(CustomerServiceKnowledge).filter(
                CustomerServiceKnowledge.shop_id == shop_id
            ).count()

    def add_customer_service(
        self,
        shop_id: int,
        title: str,
        content: str,
        tags: Optional[str] = None,
        enabled: bool = True,
    ) -> CustomerServiceKnowledge:
        """添加客服知识"""
        with self.get_session() as session:
            cs = CustomerServiceKnowledge(
                shop_id=shop_id,
                title=title,
                content=content,
                tags=tags,
                enabled=enabled,
            )
            session.add(cs)
            session.commit()
            logger.info(f"客服知识添加成功: shop_id={shop_id}, title={title}")
            self._reindex_cs(cs)
            return cs

    def update_customer_service(
        self,
        cs_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[CustomerServiceKnowledge]:
        """更新客服知识"""
        with self.get_session() as session:
            cs = session.get(CustomerServiceKnowledge, cs_id)
            if not cs:
                return None
            if title is not None:
                cs.title = title
            if content is not None:
                cs.content = content
            if tags is not None:
                cs.tags = tags
            if enabled is not None:
                cs.enabled = enabled
            session.commit()
            logger.info(f"客服知识更新成功: id={cs_id}")
            if self.vector_index_sync and cs:
                if cs.enabled:
                    self._reindex_cs(cs)
                else:
                    self._remove_vector(
                        self.vector_index_sync.remove_customer_service(cs_id, cs.shop_id)
                    )
            return cs

    def delete_customer_service(self, cs_id: int) -> bool:
        """删除客服知识"""
        with self.get_session() as session:
            cs = session.get(CustomerServiceKnowledge, cs_id)
            if not cs:
                return False
            shop_id = cs.shop_id
            session.delete(cs)
            session.commit()
            logger.info(f"客服知识删除成功: id={cs_id}")
            self._remove_vector(self.vector_index_sync.remove_customer_service(cs_id, shop_id))
            return True

    def batch_import_customer_service(
        self,
        shop_id: int,
        rows: List[Dict[str, Any]],
    ) -> tuple[int, int]:
        """批量导入客服知识，跳过重复项（同店铺内标题+内容完全相同）

        Args:
            shop_id: 店铺数据库ID
            rows: 待导入行列表，每项含 title, content, tags

        Returns:
            (success_count, skipped_count)
        """
        success = 0
        skipped = 0
        inserted: list[CustomerServiceKnowledge] = []
        with self.get_session() as session:
            for row in rows:
                title = row.get("title", "")
                content = row.get("content", "")
                tags = row.get("tags")

                # 重复检测：同店铺下标题+内容完全相同
                stmt = select(CustomerServiceKnowledge).where(
                    and_(
                        CustomerServiceKnowledge.shop_id == shop_id,
                        CustomerServiceKnowledge.title == title,
                        CustomerServiceKnowledge.content == content,
                    )
                )
                if session.scalar(stmt) is not None:
                    skipped += 1
                    continue

                cs = CustomerServiceKnowledge(
                    shop_id=shop_id,
                    title=title,
                    content=content,
                    tags=tags,
                    enabled=True,
                )
                session.add(cs)
                session.flush()
                inserted.append(cs)
                success += 1

            # 提交前触发向量索引（commit 后对象会脱离 session）
            for cs in inserted:
                self._reindex_cs(cs)

            session.commit()

        logger.info(f"批量导入客服知识: shop_id={shop_id}, success={success}, skipped={skipped}")
        return success, skipped

    def filter_customer_service_by_tag(self, shop_id: int, tag: str) -> List[CustomerServiceKnowledge]:
        """按标签筛选客服知识"""
        with self.get_session() as session:
            # LIKE 查询匹配标签
            stmt = select(CustomerServiceKnowledge).where(
                and_(
                    CustomerServiceKnowledge.shop_id == shop_id,
                    CustomerServiceKnowledge.enabled == True,
                    CustomerServiceKnowledge.tags.like(f"%{tag}%"),
                )
            ).order_by(CustomerServiceKnowledge.created_at.desc())
            return list(session.scalars(stmt))

    def get_all_tags(self, shop_id: int) -> List[str]:
        """获取店铺所有标签（去重）"""
        with self.get_session() as session:
            stmt = select(CustomerServiceKnowledge.tags).where(
                CustomerServiceKnowledge.shop_id == shop_id
            )
            tags_list = []
            for row in session.execute(stmt):
                if row[0]:
                    tags_list.extend([t.strip() for t in row[0].split(',') if t.strip()])
            # 去重
            return sorted(list(set(tags_list)))

    # ========== 批量索引 ==========

    def rebuild_bm25(self, shop_id: int, source_type: str = "product") -> None:
        """批量同步后重建 BM25 索引（只调用一次，避免逐条 O(N²) 重建）"""
        if self.vector_index_sync is None:
            return
        db_shop_id = self._resolve_shop_id(shop_id)
        self._schedule_async(
            self.vector_index_sync.rebuild_bm25_for_shop(source_type, db_shop_id)
        )

    # ========== 检索 ==========

    def _resolve_shop_id(self, shop_id: int) -> int:
        """
        将店铺原始ID转换为数据库中的Shop.id

        Args:
            shop_id: 店铺原始ID（如591119888）

        Returns:
            数据库中的Shop.id（如1），如果找不到返回原值
        """
        with self.get_session() as session:
            stmt = select(Shop).where(Shop.shop_id == str(shop_id))
            shop = session.scalar(stmt)
            if shop:
                return shop.id
            # 如果没找到，尝试直接用整数查询（兼容已有数据）
            stmt2 = select(Shop).where(Shop.id == shop_id)
            shop2 = session.scalar(stmt2)
            if shop2:
                return shop2.id
            # 找不到时返回原值，让后续查询返回空结果
            logger.warning(f"未找到店铺: shop_id={shop_id}")
            return shop_id

    def search_knowledge(
        self,
        shop_id: int,
        query: Optional[str] = None,
        goods_id: Optional[int] = None,
        limit: int = 10,
        use_hybrid: bool = True,
    ) -> Dict[str, Any]:
        """
        检索知识库

        Args:
            shop_id: 店铺原始ID
            query: 关键词查询，可为空
            goods_id: 精确查询特定商品，可为空
            limit: 返回结果最大数量
            use_hybrid: 是否使用混合检索（需 hybrid_retriever 可用）

        Returns:
            {
                "product_knowledge": [...],
                "customer_service_knowledge": [...],
                "custom_knowledge": [...],
            }
        """
        result = {
            "product_knowledge": [],
            "customer_service_knowledge": [],
            "custom_knowledge": [],
        }

        # 将店铺原始ID转换为数据库中的Shop.id
        db_shop_id = self._resolve_shop_id(shop_id)

        # 如果指定了 goods_id，精确查询产品知识
        if goods_id is not None:
            product = self.get_product_by_goods_id(db_shop_id, goods_id)
            if product:
                result["product_knowledge"] = [product]
            return result

        # 无关键词时返回最新记录
        if not query or not query.strip():
            return self._search_latest(db_shop_id, shop_id, limit, result)

        # 混合检索优先，降级为传统检索
        if use_hybrid and self.hybrid_retriever is not None:
            try:
                final = self._search_hybrid(db_shop_id, shop_id, query, limit, result)
                p_cnt = len(final.get("product_knowledge", []))
                cs_cnt = len(final.get("customer_service_knowledge", []))
                ck_cnt = len(final.get("custom_knowledge", []))
                # 向量库无数据时自动降级到 SQL LIKE 检索
                if p_cnt == 0 and cs_cnt == 0 and ck_cnt == 0:
                    logger.info("混合检索无结果，自动降级为 SQL 传统检索")
                    return self._search_legacy(db_shop_id, shop_id, query, limit, result)
                logger.info(f"search_knowledge 完成: product={p_cnt}, cs={cs_cnt}, custom={ck_cnt}")
                return final
            except Exception as e:
                logger.warning(f"混合检索失败，降级为传统检索: {e}")
                return self._search_legacy(db_shop_id, shop_id, query, limit, result)

        return self._search_legacy(db_shop_id, shop_id, query, limit, result)

    def _search_hybrid(
        self, db_shop_id: int, raw_shop_id: int, query: str, limit: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """混合检索：向量 + BM25 → 重排序 → 查询 SQL 获取完整数据"""
        import asyncio

        from config import get_config

        alpha = get_config("knowledge_base.hybrid_search_alpha", 0.5)
        has_rerank = self.reranker_service is not None
        logger.info(f"混合检索: query={query[:50]}, alpha={alpha}, reranker={'有' if has_rerank else '无'}")

        async def _do_search():
            candidates = await self.hybrid_retriever.search(
                query=query,
                shop_id=db_shop_id,
                top_k_per_source=30,
                alpha=alpha,
            )
            logger.info(f"混合检索召回: {len(candidates)} 条候选")

            if candidates and self.reranker_service:
                candidates = await self.reranker_service.rerank(
                    query=query,
                    candidates=candidates,
                    top_k=limit,
                )
                logger.info(f"重排序后: {len(candidates)} 条")
            else:
                candidates = candidates[:limit]

            return candidates

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(_do_search(), loop)
            candidates = future.result(timeout=30)
        except RuntimeError:
            candidates = asyncio.run(_do_search())

        # 按 source_type 分组，从 SQL 获取完整数据
        product_ids = []
        cs_ids = []
        custom_texts = []

        for c in candidates:
            logger.debug(f"  候选: type={c['source_type']} id={c['source_id']} score={c.get('final_score',0):.4f} text={c.get('text','')[:60]}")
            if c["source_type"] == "product" and c["source_id"] is not None:
                product_ids.append(c["source_id"])
            elif c["source_type"] == "customer_service" and c["source_id"] is not None:
                cs_ids.append(c["source_id"])
            elif c["source_type"] == "custom":
                custom_texts.append({
                    "title": c["metadata"].get("title", ""),
                    "text": c["text"],
                    "rerank_score": c.get("rerank_score", 0),
                })

        logger.info(f"混合检索结果: product={product_ids}, cs={cs_ids}, custom={len(custom_texts)}")

        with self.get_session() as session:
            if product_ids:
                stmt = select(ProductKnowledge).where(ProductKnowledge.id.in_(product_ids))
                products = {p.id: p for p in session.scalars(stmt)}
                result["product_knowledge"] = [products[pid] for pid in product_ids if pid in products]

            if cs_ids:
                stmt = select(CustomerServiceKnowledge).where(CustomerServiceKnowledge.id.in_(cs_ids))
                cs_map = {cs.id: cs for cs in session.scalars(stmt)}
                result["customer_service_knowledge"] = [cs_map[cid] for cid in cs_ids if cid in cs_map]
                for cs_item in result["customer_service_knowledge"]:
                    logger.info(f"  客服知识命中: title={cs_item.title} content={cs_item.content[:80]}")

        result["custom_knowledge"] = custom_texts
        return result

    def _search_legacy(
        self, db_shop_id: int, raw_shop_id: int, query: str, limit: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """传统 jieba + SQL LIKE 检索"""
        with self.get_session() as session:
            words = jieba.cut_for_search(query.strip())
            product_conditions = [ProductKnowledge.shop_id == db_shop_id]
            cs_conditions = [
                CustomerServiceKnowledge.shop_id == db_shop_id,
                CustomerServiceKnowledge.enabled == True,
            ]

            for word in words:
                if len(word.strip()) >= 2:
                    product_conditions.append(
                        or_(
                            ProductKnowledge.goods_name.contains(word),
                            ProductKnowledge.extracted_content.contains(word),
                        )
                    )
                    cs_conditions.append(
                        or_(
                            CustomerServiceKnowledge.title.contains(word),
                            CustomerServiceKnowledge.content.contains(word),
                        )
                    )

            stmt_p = select(ProductKnowledge).where(and_(*product_conditions))\
                .order_by(ProductKnowledge.created_at.desc())\
                .limit(limit)
            result["product_knowledge"] = list(session.scalars(stmt_p))

            stmt_cs = select(CustomerServiceKnowledge).where(and_(*cs_conditions))\
                .order_by(CustomerServiceKnowledge.created_at.desc())\
                .limit(limit)
            result["customer_service_knowledge"] = list(session.scalars(stmt_cs))

        return result

    def _search_latest(
        self, db_shop_id: int, raw_shop_id: int, limit: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """无关键词时返回最新记录"""
        with self.get_session() as session:
            stmt_p = select(ProductKnowledge).where(ProductKnowledge.shop_id == db_shop_id)\
                .order_by(ProductKnowledge.created_at.desc())\
                .limit(limit)
            result["product_knowledge"] = list(session.scalars(stmt_p))

            stmt_cs = select(CustomerServiceKnowledge).where(
                and_(
                    CustomerServiceKnowledge.shop_id == raw_shop_id,
                    CustomerServiceKnowledge.enabled == True,
                )
            ).order_by(CustomerServiceKnowledge.created_at.desc())\
                .limit(limit)
            result["customer_service_knowledge"] = list(session.scalars(stmt_cs))

        return result

    def format_search_result(
        self,
        result: Dict[str, Any],
    ) -> str:
        """
        将检索结果格式化为Agent可读的字符串

        Args:
            result: search_knowledge 返回的结果

        Returns:
            格式化后的字符串
        """
        output_parts = []

        products = result.get("product_knowledge", [])
        if products:
            output_parts.append("【产品知识】")
            for i, p in enumerate(products, 1):
                info = []
                info.append(f"{i}. {p.goods_name} (ID: {p.goods_id})")
                if p.price:
                    info.append(f"  价格: {p.price}")
                if p.image_path:
                    info.append(f"  说明书图片: 有（可调用 send_product_image 发送）")
                if p.extracted_content:
                    # 截断避免太长
                    content = p.extracted_content
                    if len(content) > 500:
                        content = content[:500] + "..."
                    info.append(f"  {content}")
                output_parts.append("\n".join(info))
                output_parts.append("")

        cs_list = result.get("customer_service_knowledge", [])
        if cs_list:
            output_parts.append("【客服知识】")
            for i, cs in enumerate(cs_list, 1):
                info = []
                info.append(f"{i}. {cs.title}")
                content = cs.content
                if len(content) > 300:
                    content = content[:300] + "..."
                info.append(f"  {content}")
                output_parts.append("\n".join(info))
                output_parts.append("")

        custom_list = result.get("custom_knowledge", [])
        if custom_list:
            output_parts.append("【自定义知识】")
            for i, ck in enumerate(custom_list, 1):
                info = []
                title = ck.get("title", "未命名")
                info.append(f"{i}. {title}")
                text = ck.get("text", "")
                if len(text) > 300:
                    text = text[:300] + "..."
                info.append(f"  {text}")
                output_parts.append("\n".join(info))
                output_parts.append("")

        final = "未找到相关知识。" if not output_parts else "\n".join(output_parts).strip()
        logger.info(f"format_search_result → LLM 将收到: {final[:200]}")
        return final

    def get_all_shops(self) -> List[Shop]:
        """获取所有店铺列表（用于UI选择器）"""
        with self.get_session() as session:
            stmt = select(Shop).order_by(Shop.shop_name.asc())
            return list(session.scalars(stmt))
