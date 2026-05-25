from abc import ABC, abstractmethod
from database import db_manager
from utils.logger_loguru import get_logger

class Channel:
    """
    渠道基类
    """
    def __init__(self):
        self.channel_name = None  # 渠道名称
        self.shop_name = None  # 店铺名称
        self.name = None  # 账号名称
        self.password = None  # 密码
        self.logger = get_logger("Channel")  
    
    async def add_shop(self, shop_id: str, shop_name: str,description: str = None) -> bool:
        """
        添加店铺
        :param shop_id: 店铺ID
        :param shop_name: 店铺名称
        :param description: 店铺描述
        :return: 是否添加成功
        """
        # 检查数据库中是否已经添加过店铺
        shop_info = db_manager.get_shop(self.channel_name, shop_id)
        if shop_info:
            self.logger.error(f"店铺 {shop_name} 已经添加过")
            return False
        # 添加店铺
        add_info=db_manager.add_shop(self.channel_name, shop_id, shop_name,description)
        if not add_info:
            self.logger.error(f"店铺 {shop_name} 添加失败")
            return False
        self.logger.info(f"店铺 {shop_name} 添加成功")
        return True


    async def remove_shop(self, shop_id: str,shop_name: str) -> bool:
        """
        删除店铺
        :param shop_id: 店铺ID
        :param shop_name: 店铺名称
        :return: 是否删除成功
        """
        # 检查数据库中是否存在店铺
        shop_info = db_manager.get_shop(self.channel_name, shop_id)
        if not shop_info:
            self.logger.error(f"店铺 {shop_name} 不存在")
            return False
        # 删除店铺
        delete_info=db_manager.delete_shop(self.channel_name, shop_id)
        if not delete_info:
            self.logger.error(f"店铺 {shop_name} 删除失败")
            return False
        self.logger.info(f"店铺 {shop_name} 删除成功")
        return True
    

    @abstractmethod
    async def start_account(self) -> None:
        """
        启动指定店铺下账号
        """
        pass

    @abstractmethod
    async def stop_account(self) -> None:
        """
        停止指定店铺下账号
        """
        pass

    @abstractmethod
    async def start_account_all(self) -> None:
        """启动所有店铺下的账号"""
        pass

    @abstractmethod
    async def stop_all(self) -> None:
        """停止所有店铺下的账号"""
        pass



