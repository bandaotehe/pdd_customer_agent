"""
全局错误通知信号
当 Agent 处理出错时，发射此信号以便 UI 提示人工介入。
参数: shop_name, error_msg, session_id
"""
from PyQt6.QtCore import QObject, pyqtSignal


class _ErrorNotifier(QObject):
    agent_error = pyqtSignal(str, str, str)
    session_updated = pyqtSignal(str, str)  # (session_id, shop_id)
    transfer_to_human = pyqtSignal(str, str, str, str, str)  # (shop_id, shop_name, customer_id, cs_name, session_id)


error_notifier = _ErrorNotifier()
