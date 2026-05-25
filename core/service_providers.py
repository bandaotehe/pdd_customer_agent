"""
服务提供者代理 - 向后兼容层

将现有的全局变量代理到底层 DI 容器。
这样旧代码（如 `from database import db_manager`）无需修改即可继续工作，
迁移成本为零。
"""

from typing import Any, Type


class _DIProxy:
    """
    懒代理，将调用转发到 DI 容器中的对应服务。

    使用方式：
        from database import db_manager
        db_manager.get_all_channels()

    内部每次从 DI 容器获取实例（DI 容器本身已做单例缓存，无需在代理层重复缓存）。
    注意：访问代理自身的特殊属性（如 __class__、__dict__）时请使用 instance() 方法。
    """

    def __init__(self, service_type: Type):
        self.__dict__["_service_type"] = service_type

    def _get_instance(self) -> Any:
        """从 DI 容器获取实例"""
        from core.di_container import container
        return container.get(self.__dict__["_service_type"])

    def __getattr__(self, name: str) -> Any:
        # 避免 __getattr__ 递归：先检查 __dict__
        if name.startswith("_") and name != "_service_type":
            raise AttributeError(name)
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            self.__dict__[name] = value
        else:
            setattr(self._get_instance(), name, value)


def _create_proxy(service_type: Type) -> _DIProxy:
    """创建指定服务的懒代理"""
    return _DIProxy(service_type)
