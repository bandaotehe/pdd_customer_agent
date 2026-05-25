# 自动回复管理器模块
from typing import Dict
from utils.logger_loguru import get_logger
from .threads import AutoReplyThread


class AutoReplyManager:
    """自动回复管理器 - 管理所有账号的自动回复连接"""

    def __init__(self):
        self.running_accounts: Dict[str, 'AutoReplyThread'] = {}  # 正在运行的账号线程
        self.logger = get_logger("AutoReplyManager")

    def start_auto_reply(self, account_data: dict) -> bool:
        """启动账号自动回复"""
        try:
            account_key = f"{account_data['channel_name']}_{account_data['shop_id']}_{account_data['username']}"

            # 检查是否已经在运行
            if account_key in self.running_accounts:
                self.logger.warning(f"账号 {account_data['username']} (店铺: {account_data['shop_id']}) 自动回复已在运行")
                return False

            # 创建并启动自动回复线程
            thread = AutoReplyThread(account_data)
            self.running_accounts[account_key] = thread

            # 连接信号
            thread.connection_success.connect(lambda: self._on_connection_success(account_key))
            thread.connection_failed.connect(lambda error: self._on_connection_failed(account_key, error))
            thread.finished.connect(lambda: self._on_thread_finished(account_key))

            # 启动线程
            self.logger.info(f"启动账号 {account_data['username']} (店铺: {account_data['shop_id']}) 自动回复")
            thread.start()
            return True

        except Exception as e:
            self.logger.error(f"启动账号 {account_data.get('username')} (店铺: {account_data.get('shop_id')}) 自动回复失败: {str(e)}")
            return False

    def stop_auto_reply(self, account_data: dict) -> bool:
        """停止账号自动回复"""
        try:
            account_key = f"{account_data['channel_name']}_{account_data['shop_id']}_{account_data['username']}"

            if account_key not in self.running_accounts:
                self.logger.warning(f"账号 {account_data['username']} (店铺: {account_data['shop_id']}) 自动回复未在运行")
                return False

            # 停止线程
            thread = self.running_accounts[account_key]
            thread.stop()

            # 等待线程结束后再从列表中移除
            if thread.isRunning():
                thread.wait(5000)  # 最多等待5秒

            # 从运行列表中移除
            if account_key in self.running_accounts:
                del self.running_accounts[account_key]

            self.logger.info(f"账号 {account_data['username']} (店铺: {account_data['shop_id']}) 自动回复已停止")
            return True

        except Exception as e:
            self.logger.error(f"停止账号 {account_data.get('username')} (店铺: {account_data.get('shop_id')}) 自动回复失败: {str(e)}")
            return False

    def is_running(self, account_data: dict) -> bool:
        """检查账号是否正在自动回复"""
        try:
            account_key = f"{account_data['channel_name']}_{account_data['shop_id']}_{account_data['username']}"

            # 检查是否在运行列表中
            if account_key not in self.running_accounts:
                return False

            thread = self.running_accounts[account_key]

            # 检查线程是否存在且正在运行
            if not thread or not hasattr(thread, 'isRunning'):
                self._cleanup_stale_thread(account_key)
                return False

            # 检查线程是否正在运行
            is_thread_running = thread.isRunning()

            # 如果线程已停止，清理引用
            if not is_thread_running:
                self._cleanup_stale_thread(account_key)
                return False

            return True

        except Exception as e:
            self.logger.error(f"检查账号运行状态失败: {str(e)}")
            return False

    def _cleanup_stale_thread(self, account_key: str):
        """清理已停止的线程引用"""
        try:
            if account_key in self.running_accounts:
                thread = self.running_accounts[account_key]
                if hasattr(thread, 'isRunning') and not thread.isRunning():
                    del self.running_accounts[account_key]
                    self.logger.debug(f"清理已停止的线程引用: {account_key}")
        except Exception as e:
            self.logger.error(f"清理线程引用失败: {account_key}, {e}")

    def _on_connection_success(self, account_key: str):
        """连接成功回调"""
        self.logger.debug(f"账号 {account_key} 自动回复连接成功")

    def _on_connection_failed(self, account_key: str, error: str):
        """连接失败回调"""
        self.logger.error(f"账号 {account_key} 自动回复连接失败: {error}")
        if account_key in self.running_accounts:
            del self.running_accounts[account_key]

    def _on_thread_finished(self, account_key: str):
        """线程结束回调"""
        self.logger.debug(f"账号 {account_key} 自动回复线程已结束")
        if account_key in self.running_accounts:
            del self.running_accounts[account_key]

    def get_running_count(self) -> int:
        """获取正在运行的账号数量"""
        return len(self.running_accounts)

    def stop_all(self):
        """停止所有自动回复"""
        try:
            for account_key, thread in self.running_accounts.items():
                if thread.is_running():
                    thread.stop()

            for thread in self.running_accounts.values():
                thread.wait(5000)

            self.running_accounts.clear()
            self.logger.info("所有自动回复任务已停止")

        except Exception as e:
            self.logger.error(f"停止所有自动回复失败: {e}")


# 全局自动回复管理器实例
auto_reply_manager = AutoReplyManager()


__all__ = ['AutoReplyManager', 'auto_reply_manager']
