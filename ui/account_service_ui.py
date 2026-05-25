"""
账号与客服管理 — 合并页面

使用 SegmentedWidget 两个标签页切换：
- 标签 1：账号管理（增删改查 + 验证登录）
- 标签 2：自动回复（上线/离线/开始回复控制）

标签页采用懒加载，第一次切到时才创建对应视图。
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QStackedWidget
from qfluentwidgets import SegmentedWidget

from ui.theme import SPACING


class AccountServiceUI(QFrame):
    """账号与客服管理 — 双标签页合并视图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("account-service")

        self._user_tab = None
        self._auto_reply_tab = None
        self._loaded = {"accounts": False, "auto_reply": False}

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["page_margin"], SPACING["page_margin"],
                                  SPACING["page_margin"], SPACING["page_margin"])
        layout.setSpacing(16)

        # 标签页切换器（用 onClick 回调，和 Knowledge_ui.py 保持一致）
        self._segmented = SegmentedWidget(self)
        self._segmented.addItem(
            routeKey="accountRoute",
            text="账号管理",
            onClick=lambda: self._switch_to("accounts"),
        )
        self._segmented.addItem(
            routeKey="autoReplyRoute",
            text="自动回复",
            onClick=lambda: self._switch_to("auto_reply"),
        )
        self._segmented.setCurrentItem("accountRoute")
        self._segmented.setFixedWidth(280)

        pivot_layout = QHBoxLayout()
        pivot_layout.addStretch()
        pivot_layout.addWidget(self._segmented)
        pivot_layout.addStretch()
        layout.addLayout(pivot_layout)

        # 内容栈
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        # 默认加载第一个标签
        self._switch_to("accounts")

    def _switch_to(self, tab_key: str):
        """切换到指定标签页（首次切到时懒加载）"""
        if tab_key == "accounts":
            if not self._loaded["accounts"]:
                self._load_accounts_tab()
            else:
                self._stack.setCurrentWidget(self._user_tab)
        elif tab_key == "auto_reply":
            if not self._loaded["auto_reply"]:
                self._load_auto_reply_tab()
            else:
                self._stack.setCurrentWidget(self._auto_reply_tab)

    def _load_accounts_tab(self):
        """加载账号管理标签（增删改查 + 验证登录）"""
        from ui.user_ui import UserManagerWidget
        self._user_tab = UserManagerWidget(self)
        self._stack.addWidget(self._user_tab)
        self._stack.setCurrentWidget(self._user_tab)
        self._loaded["accounts"] = True

    def _load_auto_reply_tab(self):
        """加载自动回复标签（上线/离线/开始回复）"""
        from ui.auto_reply_ui import AutoReplyUI
        self._auto_reply_tab = AutoReplyUI(self)
        self._stack.addWidget(self._auto_reply_tab)
        self._stack.setCurrentWidget(self._auto_reply_tab)
        self._loaded["auto_reply"] = True

    def showEvent(self, event):
        super().showEvent(event)
        # 导航切换回本页面时，确保显示当前选中标签的内容
        route = self._segmented.currentItem()
        if route == "accountRoute" and self._user_tab:
            self._stack.setCurrentWidget(self._user_tab)
        elif route == "autoReplyRoute" and self._auto_reply_tab:
            self._stack.setCurrentWidget(self._auto_reply_tab)
