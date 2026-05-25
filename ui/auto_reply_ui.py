# 自动回复界面 - 兼容层
# 新代码已移动到 ui/auto_reply/ 包中

# 为了保持向后兼容，重新导出所有内容
from ui.auto_reply import (
    LogoLoaderThread,
    AutoReplyThread,
    SetStatusThread,
    AutoReplyManager,
    auto_reply_manager,
    AutoReplyCard,
    AutoReplyUI,
)

__all__ = [
    'LogoLoaderThread',
    'AutoReplyThread',
    'SetStatusThread',
    'AutoReplyManager',
    'auto_reply_manager',
    'AutoReplyCard',
    'AutoReplyUI',
]
