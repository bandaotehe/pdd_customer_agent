"""
缓存机制 - 提供内存缓存功能，支持TTL和LRU策略
"""

import asyncio
import time
from typing import Any, Optional, Dict, Tuple, Callable, Union
from threading import RLock
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from utils.logger_loguru import get_logger

class CacheEvictionPolicy(Enum):
    """缓存淘汰策略"""
    LRU = "lru"           # 最近最少使用
    FIFO = "fifo"         # 先进先出
    TTL = "ttl"           # 基于时间
    LFU = "lfu"           # 最少使用频率

@dataclass
class CacheItem:
    """缓存项"""
    value: Any
    expire_time: Optional[float] = None
    access_count: int = 0
    last_access_time: float = 0
    created_time: float = 0

    def __post_init__(self):
        if self.created_time == 0:
            self.created_time = time.time()
        if self.last_access_time == 0:
            self.last_access_time = time.time()

    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expire_time is None:
            return False
        return time.time() > self.expire_time

    def access(self):
        """访问缓存项"""
        self.access_count += 1
        self.last_access_time = time.time()

class MemoryCache:
    """内存缓存 - 支持TTL和LRU策略"""

    def __init__(self,
                 max_size: int = 1000,
                 default_ttl: Optional[int] = None,
                 eviction_policy: CacheEvictionPolicy = CacheEvictionPolicy.LRU,
                 cleanup_interval: float = 60.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.eviction_policy = eviction_policy
        self.cleanup_interval = cleanup_interval

        self._cache: Dict[str, CacheItem] = {}
        self._lock = RLock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self.logger = get_logger("MemoryCache")

        # LRU需要的有序字典
        if eviction_policy == CacheEvictionPolicy.LRU:
            self._access_order = OrderedDict()

        # 启动清理任务
        if cleanup_interval > 0:
            self._start_cleanup_task()

    def __del__(self):
        """析构函数"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]

            # 检查是否过期
            if item.is_expired:
                self._remove_item(key)
                return None

            # 更新访问信息
            item.access()
            self._update_access_order(key)

            return item.value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            expire_time = None
            if ttl is not None:
                expire_time = time.time() + ttl
            elif self.default_ttl is not None:
                expire_time = time.time() + self.default_ttl

            with self._lock:
                # 检查是否需要淘汰
                if key not in self._cache and len(self._cache) >= self.max_size:
                    self._evict_items()

                # 创建缓存项
                item = CacheItem(
                    value=value,
                    expire_time=expire_time
                )

                self._cache[key] = item
                self._update_access_order(key)

                self.logger.debug(f"缓存设置: {key}")
                return True

        except Exception as e:
            self.logger.error(f"缓存设置失败 {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存项"""
        with self._lock:
            if key not in self._cache:
                return False

            self._remove_item(key)
            self.logger.debug(f"缓存删除: {key}")
            return True

    async def exists(self, key: str) -> bool:
        """检查缓存项是否存在且未过期"""
        with self._lock:
            if key not in self._cache:
                return False

            item = self._cache[key]
            if item.is_expired:
                self._remove_item(key)
                return False

            return True

    async def clear(self) -> int:
        """清空所有缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()

            if self.eviction_policy == CacheEvictionPolicy.LRU:
                self._access_order.clear()

            self.logger.info(f"缓存已清空，清除了 {count} 项")
            return count

    async def get_size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)

    async def cleanup_expired(self) -> int:
        """清理过期的缓存项"""
        with self._lock:
            expired_keys = [
                key for key, item in self._cache.items()
                if item.is_expired
            ]

            for key in expired_keys:
                self._remove_item(key)

            if expired_keys:
                self.logger.debug(f"清理过期缓存: {len(expired_keys)} 项")

            return len(expired_keys)

    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_items = len(self._cache)
            expired_items = sum(1 for item in self._cache.values() if item.is_expired)

            # 计算平均访问次数
            if total_items > 0:
                avg_access_count = sum(item.access_count for item in self._cache.values()) / total_items
            else:
                avg_access_count = 0

            return {
                "total_items": total_items,
                "expired_items": expired_items,
                "max_size": self.max_size,
                "usage_ratio": total_items / self.max_size,
                "eviction_policy": self.eviction_policy.value,
                "default_ttl": self.default_ttl,
                "avg_access_count": avg_access_count
            }

    def get_keys(self) -> list:
        """获取所有缓存键"""
        with self._lock:
            return list(self._cache.keys())

    def _remove_item(self, key: str):
        """移除缓存项"""
        if key in self._cache:
            del self._cache[key]

        if self.eviction_policy == CacheEvictionPolicy.LRU and key in self._access_order:
            del self._access_order[key]

    def _update_access_order(self, key: str):
        """更新访问顺序"""
        if self.eviction_policy == CacheEvictionPolicy.LRU:
            if key in self._access_order:
                del self._access_order[key]
            self._access_order[key] = True

    def _evict_items(self):
        """淘汰缓存项"""
        if not self._cache:
            return

        evict_count = max(1, self.max_size // 10)  # 淘汰10%

        if self.eviction_policy == CacheEvictionPolicy.LRU:
            # LRU: 淘汰最近最少使用的
            keys_to_evict = list(self._access_order.keys())[:evict_count]
            for key in keys_to_evict:
                self._remove_item(key)

        elif self.eviction_policy == CacheEvictionPolicy.FIFO:
            # FIFO: 按创建时间淘汰最早的
            items_sorted = sorted(
                self._cache.items(),
                key=lambda x: x[1].created_time
            )
            keys_to_evict = [key for key, _ in items_sorted[:evict_count]]
            for key in keys_to_evict:
                self._remove_item(key)

        elif self.eviction_policy == CacheEvictionPolicy.LFU:
            # LFU: 淘汰使用频率最低的
            items_sorted = sorted(
                self._cache.items(),
                key=lambda x: x[1].access_count
            )
            keys_to_evict = [key for key, _ in items_sorted[:evict_count]]
            for key in keys_to_evict:
                self._remove_item(key)

        self.logger.debug(f"淘汰缓存项: {evict_count} 个")

    def _start_cleanup_task(self):
        """启动清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self.cleanup_interval)
                    await self.cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"缓存清理任务错误: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def close(self):
        """关闭缓存"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.clear()
        self.logger.info("内存缓存已关闭")

class CacheManager:
    """缓存管理器 - 管理多个缓存实例"""

    def __init__(self):
        self._caches: Dict[str, MemoryCache] = {}
        self._lock = RLock()
        self.logger = get_logger("CacheManager")

    def get_cache(self, name: str, **kwargs) -> MemoryCache:
        """获取或创建缓存实例"""
        with self._lock:
            if name not in self._caches:
                self._caches[name] = MemoryCache(**kwargs)
                self.logger.debug(f"创建缓存实例: {name}")
            return self._caches[name]

    async def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            for name, cache in self._caches.items():
                await cache.clear()
            self.logger.info("所有缓存已清空")

    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有缓存的统计信息"""
        with self._lock:
            stats = {}
            for name, cache in self._caches.items():
                stats[name] = await cache.get_stats()
            return stats

    async def close_all(self):
        """关闭所有缓存"""
        with self._lock:
            for name, cache in self._caches.items():
                await cache.close()
            self._caches.clear()
            self.logger.info("所有缓存已关闭")


# 全局缓存管理器实例
cache_manager = CacheManager()

# 便捷函数
async def cache_get(cache_name: str, key: str) -> Optional[Any]:
    """便捷的缓存获取函数"""
    cache = cache_manager.get_cache(cache_name)
    return await cache.get(key)

async def cache_set(cache_name: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """便捷的缓存设置函数"""
    cache = cache_manager.get_cache(cache_name)
    return await cache.set(key, value, ttl)