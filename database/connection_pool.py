"""
数据库连接池 - 提供高效的数据库连接管理
"""

import asyncio
import threading
import sqlite3
import time
from contextlib import contextmanager
from queue import Queue, Empty, Full
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import weakref

from utils.logger_loguru import get_logger
from core.base_service import BaseService, HealthCheckable


class ConnectionStatus(Enum):
    """连接状态"""
    IDLE = "idle"           # 空闲
    IN_USE = "in_use"       # 使用中
    EXPIRED = "expired"     # 已过期
    ERROR = "error"         # 错误状态


@dataclass
class ConnectionWrapper:
    """连接包装器"""
    connection: sqlite3.Connection
    created_at: float
    last_used: float
    usage_count: int = 0
    status: ConnectionStatus = ConnectionStatus.IDLE
    is_in_transaction: bool = False

    def __post_init__(self):
        if self.last_used == 0:
            self.last_used = self.created_at

    def touch(self):
        """更新最后使用时间和使用次数"""
        self.last_used = time.time()
        self.usage_count += 1

    def close(self):
        """关闭连接"""
        try:
            if self.connection and not self.connection.closed:
                self.connection.close()
        except Exception:
            pass

    def is_valid(self, max_idle_time: float = 3600) -> bool:
        """检查连接是否有效"""
        if not self.connection or self.connection.closed:
            return False

        if self.status == ConnectionStatus.ERROR:
            return False

        # 检查是否超时
        if time.time() - self.last_used > max_idle_time:
            return False

        return True


class ConnectionPool(BaseService, HealthCheckable):
    """SQLite连接池"""

    def __init__(self,
                 database_path: str,
                 max_connections: int = 10,
                 min_connections: int = 2,
                 max_idle_time: float = 3600,
                 connection_timeout: float = 30.0,
                 max_lifetime: float = 7200,
                 logger=None):
        """
        初始化连接池

        Args:
            database_path: 数据库文件路径
            max_connections: 最大连接数
            min_connections: 最小连接数
            max_idle_time: 最大空闲时间（秒）
            connection_timeout: 获取连接超时时间（秒）
            max_lifetime: 连接最大生命周期（秒）
        """
        super().__init__(logger)
        self.database_path = database_path
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.max_idle_time = max_idle_time
        self.connection_timeout = connection_timeout
        self.max_lifetime = max_lifetime

        # 连接池
        self._pool: Queue[ConnectionWrapper] = Queue(maxsize=max_connections)
        self._active_connections: Dict[int, ConnectionWrapper] = {}
        self._lock = threading.RLock()

        # 统计信息
        self._total_created = 0
        self._total_closed = 0
        self._peak_connections = 0
        self._reused_connections = 0

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 60.0  # 清理间隔

        # 弱引用跟踪
        self._connection_refs: List[weakref.ref] = []

    def initialize(self) -> bool:
        """初始化连接池"""
        try:
            # 创建最小数量的连接
            for _ in range(self.min_connections):
                wrapper = self._create_connection()
                if wrapper:
                    self._pool.put(wrapper)
                    self._total_created += 1

            # 启动清理任务
            self._start_cleanup_task()

            self._initialized = True
            self.logger.info(f"连接池初始化成功: {self.database_path} (最小连接数: {self.min_connections})")
            return True

        except Exception as e:
            return self.handle_exception(e, "连接池初始化失败")

    def _create_connection(self) -> Optional[ConnectionWrapper]:
        """创建新连接"""
        try:
            connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                timeout=self.connection_timeout
            )

            # 设置连接属性
            connection.row_factory = sqlite3.Row  # 返回字典式行
            connection.execute("PRAGMA foreign_keys=ON")  # 启用外键约束
            connection.execute("PRAGMA journal_mode=WAL")  # 启用WAL模式
            connection.execute("PRAGMA synchronous=NORMAL")  # 设置同步模式

            wrapper = ConnectionWrapper(
                connection=connection,
                created_at=time.time(),
                last_used=time.time()
            )

            return wrapper

        except Exception as e:
            self.logger.error(f"创建数据库连接失败: {e}")
            return None

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        wrapper = None
        connection_id = None

        try:
            wrapper = self._acquire_connection()
            if not wrapper:
                raise RuntimeError("无法获取数据库连接")

            connection_id = id(wrapper.connection)
            wrapper.status = ConnectionStatus.IN_USE
            wrapper.touch()

            yield wrapper.connection

        except Exception as e:
            # 标记连接为错误状态
            if wrapper:
                wrapper.status = ConnectionStatus.ERROR
            raise

        finally:
            if wrapper:
                wrapper.status = ConnectionStatus.IDLE
                wrapper.last_used = time.time()

                # 如果连接有效，放回池中
                if wrapper.is_valid(self.max_idle_time):
                    self._release_connection(wrapper)
                else:
                    # 连接无效，关闭并创建新连接补充
                    self._close_connection(wrapper)
                    self._recreate_connection()

                if connection_id:
                    self._active_connections.pop(connection_id, None)

    def _acquire_connection(self) -> Optional[ConnectionWrapper]:
        """获取连接"""
        with self._lock:
            # 尝试从池中获取连接
            try:
                wrapper = self._pool.get(timeout=self.connection_timeout)
                if wrapper.is_valid():
                    self._reused_connections += 1
                    self._active_connections[id(wrapper.connection)] = wrapper
                    return wrapper
                else:
                    # 连接无效，创建新连接
                    self._close_connection(wrapper)
            except Empty:
                pass

            # 池中没有可用连接，尝试创建新连接
            if len(self._active_connections) < self.max_connections:
                wrapper = self._create_connection()
                if wrapper:
                    self._total_created += 1
                    self._active_connections[id(wrapper.connection)] = wrapper
                    return wrapper

            # 等待连接释放
            self.logger.warning("连接池已满，等待连接释放")
            try:
                wrapper = self._pool.get(timeout=self.connection_timeout)
                if wrapper.is_valid():
                    self._active_connections[id(wrapper.connection)] = wrapper
                    return wrapper
                else:
                    self._close_connection(wrapper)
            except Empty:
                pass

            raise RuntimeError("无法获取数据库连接：连接池已满且无可用连接")

    def _release_connection(self, wrapper: ConnectionWrapper):
        """释放连接回池"""
        try:
            self._pool.put(wrapper, timeout=1.0)
        except Full:
            # 池满，直接关闭连接
            self._close_connection(wrapper)

    def _close_connection(self, wrapper: ConnectionWrapper):
        """关闭连接"""
        try:
            wrapper.close()
            self._total_closed += 1
        except Exception as e:
            self.logger.error(f"关闭数据库连接失败: {e}")

    def _recreate_connection(self):
        """重新创建连接以维持最小连接数"""
        try:
            current_size = self._pool.qsize() + len(self._active_connections)
            if current_size < self.min_connections:
                wrapper = self._create_connection()
                if wrapper:
                    self._pool.put(wrapper)
                    self._total_created += 1
        except Exception as e:
            self.logger.error(f"重新创建连接失败: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 尝试获取一个连接并执行简单查询
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            # 获取连接池状态
            with self._lock:
                pool_size = self._pool.qsize()
                active_count = len(self._active_connections)
                total_connections = pool_size + active_count

            status = "healthy"
            if total_connections == 0:
                status = "unhealthy"
            elif total_connections < self.min_connections:
                status = "degraded"

            return {
                "status": status,
                "database_path": self.database_path,
                "pool_size": pool_size,
                "active_connections": active_count,
                "total_connections": total_connections,
                "max_connections": self.max_connections,
                "min_connections": self.min_connections,
                "total_created": self._total_created,
                "total_closed": self._total_closed,
                "reused_connections": self._reused_connections,
                "peak_connections": self._peak_connections,
                "reuse_rate": (self._reused_connections / max(1, self._total_created)) * 100,
                "timestamp": time.time()
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "database_path": self.database_path,
                "timestamp": time.time()
            }

    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._lock:
            pool_size = self._pool.qsize()
            active_count = len(self._active_connections)
            total_connections = pool_size + active_count

            return {
                "total_connections": total_connections,
                "active_connections": active_count,
                "idle_connections": pool_size,
                "max_connections": self.max_connections,
                "min_connections": self.min_connections,
                "total_created": self._total_created,
                "total_closed": self._total_closed,
                "reused_connections": self._reused_connections,
                "peak_connections": self._peak_connections,
                "utilization": (total_connections / self.max_connections) * 100,
                "reuse_rate": (self._reused_connections / max(1, self._total_created)) * 100
            }

    async def cleanup_expired_connections(self):
        """清理过期连接"""
        with self._lock:
            expired_connections = []
            temp_connections = []

            # 检查池中的连接
            while not self._pool.empty():
                try:
                    wrapper = self._pool.get_nowait()
                    if wrapper.is_valid(self.max_idle_time):
                        temp_connections.append(wrapper)
                    else:
                        expired_connections.append(wrapper)
                except Empty:
                    break

            # 将有效连接放回池中
            for wrapper in temp_connections:
                self._pool.put(wrapper)

            # 关闭过期连接
            for wrapper in expired_connections:
                self._close_connection(wrapper)

            # 重新创建连接以维持最小连接数
            while self._pool.qsize() < self.min_connections:
                wrapper = self._create_connection()
                if wrapper:
                    self._pool.put(wrapper)
                    self._total_created += 1
                else:
                    break

        if expired_connections:
            self.logger.debug(f"清理了 {len(expired_connections)} 个过期连接")

    def _start_cleanup_task(self):
        """启动清理任务"""
        async def cleanup_loop():
            while not self._disposed:
                try:
                    await asyncio.sleep(self.cleanup_interval)
                    await self.cleanup_expired_connections()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"连接池清理任务错误: {e}")
                    await asyncio.sleep(10.0)

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    def dispose(self):
        """释放连接池资源"""
        try:
            # 停止清理任务
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                try:
                    asyncio.run(self._cleanup_task)
                except asyncio.CancelledError:
                    pass

            # 关闭所有连接
            with self._lock:
                # 关闭池中的连接
                while not self._pool.empty():
                    try:
                        wrapper = self._pool.get_nowait()
                        self._close_connection(wrapper)
                    except Empty:
                        break

                # 关闭活动连接
                for wrapper in self._active_connections.values():
                    self._close_connection(wrapper)

                self._active_connections.clear()

            self._disposed = True
            self.logger.info("数据库连接池已释放")

        except Exception as e:
            self.handle_exception(e, "释放连接池失败")


# 全局连接池管理器
class ConnectionPoolManager:
    """连接池管理器"""

    def __init__(self):
        self._pools: Dict[str, ConnectionPool] = {}
        self._lock = threading.RLock()
        self.logger = get_logger("ConnectionPoolManager")

    def get_pool(self, database_path: str, **kwargs) -> ConnectionPool:
        """获取或创建连接池"""
        with self._lock:
            if database_path not in self._pools:
                pool = ConnectionPool(database_path, **kwargs)
                self._pools[database_path] = pool
                self.logger.debug(f"创建连接池: {database_path}")
            return self._pools[database_path]

    def close_pool(self, database_path: str) -> bool:
        """关闭指定数据库的连接池"""
        with self._lock:
            if database_path in self._pools:
                pool = self._pools[database_path]
                pool.dispose()
                del self._pools[database_path]
                self.logger.debug(f"关闭连接池: {database_path}")
                return True
            return False

    async def close_all_pools(self):
        """关闭所有连接池"""
        with self._lock:
            for database_path, pool in list(self._pools.items()):
                pool.dispose()
            self._pools.clear()
            self.logger.info("所有连接池已关闭")

    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有连接池的统计信息"""
        with self._lock:
            stats = {}
            for database_path, pool in self._pools.items():
                try:
                    stats[database_path] = pool.get_stats()
                except Exception as e:
                    stats[database_path] = {"error": str(e)}
            return stats

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """对所有连接池进行健康检查"""
        with self._lock:
            results = {}
            for database_path, pool in self._pools.items():
                try:
                    results[database_path] = await pool.health_check()
                except Exception as e:
                    results[database_path] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            return results


# 全局连接池管理器实例
pool_manager = ConnectionPoolManager()

# 便捷函数
def get_connection_pool(database_path: str, **kwargs) -> ConnectionPool:
    """获取连接池的便捷函数"""
    return pool_manager.get_pool(database_path, **kwargs)

@contextmanager
def get_db_connection(database_path: str, **kwargs):
    """获取数据库连接的便捷函数"""
    pool = get_connection_pool(database_path, **kwargs)
    with pool.get_connection() as conn:
        yield conn