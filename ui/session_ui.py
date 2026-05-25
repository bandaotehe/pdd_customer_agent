"""
会话管理页面
按店铺分类查看和管理 AI 对话记录。
米白/奶油白小清新风格，带视图切换动画。
"""
from datetime import datetime
from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QPropertyAnimation,
                           QEasingCurve, QPoint, QParallelAnimationGroup,
                           QSequentialAnimationGroup)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QWidget, QLabel,
                              QStackedWidget, QScrollArea, QGraphicsOpacityEffect,
                              QSizePolicy, QMessageBox)
from PyQt6.QtGui import QColor, QPalette
from qfluentwidgets import (CardWidget, SubtitleLabel, CaptionLabel, BodyLabel,
                             StrongBodyLabel, PushButton, ScrollArea,
                             InfoBadge, FluentIcon as FIF)
from utils.logger_loguru import get_logger
from ui.theme import COLORS, CARD, SPACING, scrollbar_style

logger = get_logger("SessionUI")

# ── 页面专属 QSS ──
_PAGE_QSS = f"""
SessionPage {{
    background-color: {COLORS['page_bg']};
}}

#leftPanel {{
    background-color: {COLORS['panel_bg']};
    border-right: 1px solid {COLORS['divider']};
    border-radius: 16px;
}}

#rightPanel {{
    background-color: {COLORS['card_bg']};
    border-radius: 16px;
}}
"""

STYLE = _PAGE_QSS + scrollbar_style()

# ==============================================================================
# 延迟加载 SessionManager（与 Agent 共用同一 DB）
# ==============================================================================
_session_manager = None

def _get_session_manager():
    global _session_manager
    if _session_manager is None:
        import sys
        from config import get_config

        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后：直接 import，模块已在 _internal 中
            from Agent.CustomerAgent.custom.session_manager import SessionManager
        else:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location(
                "session_manager",
                Path(__file__).resolve().parents[1]
                / "Agent" / "CustomerAgent" / "custom" / "session_manager.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            SessionManager = mod.SessionManager

        db_path = get_config("db_path", "./temp/agent.db")
        _session_manager = SessionManager(db_path=db_path)
    return _session_manager


# ==============================================================================
# ShopCard — 左侧店铺卡片
# ==============================================================================
class ShopCard(QFrame):
    shop_selected = pyqtSignal(str)

    def __init__(self, shop_id: str, shop_name: str, session_count: int,
                 error_count: int = 0, transfer_count: int = 0, parent=None):
        super().__init__(parent)
        self._shop_id = shop_id
        self._selected = False
        self._count_badge = None
        self._error_badge = None
        self._transfer_badge = None
        self._badge_layout = None
        self.setupUI(shop_name, session_count, error_count, transfer_count)

    def setupUI(self, shop_name: str, session_count: int, error_count: int, transfer_count: int = 0):
        self.setFixedHeight(76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("shopCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        name = StrongBodyLabel(shop_name or f"店铺 {self._shop_id}")
        name.setWordWrap(True)
        name.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px;")
        layout.addWidget(name)

        id_label = CaptionLabel(f"ID: {self._shop_id}")
        id_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        layout.addWidget(id_label)

        self._badge_layout = QHBoxLayout()
        self._badge_layout.setSpacing(6)
        self._count_badge = InfoBadge.info(f"{session_count} 个会话")
        self._badge_layout.addWidget(self._count_badge)
        if transfer_count > 0:
            self._transfer_badge = InfoBadge.error(f"{transfer_count} 转人工")
            self._badge_layout.addWidget(self._transfer_badge)
        else:
            self._transfer_badge = None
        if error_count > 0:
            self._error_badge = InfoBadge.warning(f"{error_count} 异常")
            self._badge_layout.addWidget(self._error_badge)
        else:
            self._error_badge = None
        self._badge_layout.addStretch()
        layout.addLayout(self._badge_layout)

        self._update_style(False)

    def _update_style(self, selected: bool):
        bg = COLORS['card_selected'] if selected else COLORS['card_bg']
        left_border = f"border-left: 4px solid {COLORS['accent_green']};" if selected else ""
        self.setStyleSheet(f"""
            #shopCard {{
                background-color: {bg};
                border-radius: 14px;
                margin: 2px 4px;
                {left_border}
            }}
            #shopCard:hover {{
                background-color: {COLORS['card_hover']};
            }}
        """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style(selected)

    def update_counts(self, session_count: int, error_count: int, transfer_count: int = 0):
        """轻量更新会话、转人工和错误计数，无需重建整个卡片"""
        if self._count_badge:
            self._badge_layout.removeWidget(self._count_badge)
            self._count_badge.deleteLater()
        self._count_badge = InfoBadge.info(f"{session_count} 个会话")
        self._badge_layout.insertWidget(0, self._count_badge)

        if self._transfer_badge:
            self._badge_layout.removeWidget(self._transfer_badge)
            self._transfer_badge.deleteLater()
            self._transfer_badge = None

        if transfer_count > 0:
            self._transfer_badge = InfoBadge.error(f"{transfer_count} 转人工")
            self._badge_layout.insertWidget(1, self._transfer_badge)

        if self._error_badge:
            self._badge_layout.removeWidget(self._error_badge)
            self._error_badge.deleteLater()
            self._error_badge = None

        if error_count > 0:
            self._error_badge = InfoBadge.warning(f"{error_count} 异常")
            self._badge_layout.insertWidget(1 if self._transfer_badge is None else 2, self._error_badge)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.shop_selected.emit(self._shop_id)
        super().mouseReleaseEvent(event)


# ==============================================================================
# ConversationCard — 会话列表卡片
# ==============================================================================
class ConversationCard(QFrame):
    session_selected = pyqtSignal(str)

    def __init__(self, session_data: dict, parent=None):
        super().__init__(parent)
        self._session_data = session_data
        self._is_error = session_data.get('is_error', False)
        self._needs_human = session_data.get('needs_human', False)
        self.setupUI()

    def setupUI(self):
        self.setFixedHeight(82)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("convCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        customer = self._session_data.get('user_id', '未知客户')
        user_label = StrongBodyLabel(f"客户: {customer}")
        user_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px;")
        header.addWidget(user_label)
        header.addStretch()

        count = self._session_data.get('message_count', 0)
        count_badge = InfoBadge.info(f"{count} 条")
        header.addWidget(count_badge)
        if self._needs_human:
            header.addWidget(InfoBadge.error("需人工"))
        elif self._is_error:
            header.addWidget(InfoBadge.warning("异常"))
        layout.addLayout(header)

        preview = self._session_data.get('last_message_preview', '') or '暂无消息'
        preview_label = BodyLabel(preview)
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(preview_label)

        last_active = self._session_data.get('last_activity_at', '')
        if last_active:
            try:
                dt = datetime.fromisoformat(last_active)
                last_active = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass
        time_label = CaptionLabel(f"最后活跃: {last_active}")
        time_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        layout.addWidget(time_label)

        if self._needs_human:
            left_border = f"border-left: 4px solid {COLORS['accent_error']};"
        elif self._is_error:
            left_border = f"border-left: 4px solid #e8b84b;"
        else:
            left_border = ""
        self.setStyleSheet(f"""
            #convCard {{
                background-color: {COLORS['card_bg']};
                border-radius: 14px;
                margin: 2px 8px;
                {left_border}
            }}
            #convCard:hover {{
                background-color: {COLORS['card_hover']};
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.session_selected.emit(self._session_data.get('session_id', ''))
        super().mouseReleaseEvent(event)


# ==============================================================================
# AvatarWidget — 消息头像
# ==============================================================================
class AvatarWidget(QLabel):
    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        color = COLORS['accent_green'] if role == 'user' else COLORS['accent_blue']
        initials = "客" if role == 'user' else "AI"
        self.setText(initials)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: {COLORS['text_primary']};
                border-radius: 18px;
                font-size: 13px;
                font-weight: bold;
            }}
        """)


# ==============================================================================
# MessageBubble — 聊天气泡
# ==============================================================================
class MessageBubble(QFrame):
    def __init__(self, role: str, content: str, timestamp: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self.setupUI(content, timestamp)

    def setupUI(self, content: str, timestamp: str):
        self.setObjectName("bubble")
        is_user = (self._role == 'user')

        outer = QHBoxLayout(self)
        outer.setContentsMargins(15, 6, 6, 15)

        if is_user:
            # 用户消息：左对齐
            avatar = AvatarWidget('user')
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            outer.addSpacing(10)

            bubble = self._make_bubble(content, timestamp, is_user)
            outer.addWidget(bubble, 0)
            outer.addStretch(1)
        else:
            # Agent 消息：右对齐
            outer.addStretch(1)

            bubble = self._make_bubble(content, timestamp, is_user)
            outer.addWidget(bubble, 0)
            outer.addSpacing(10)

            avatar = AvatarWidget('assistant')
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

    def _make_bubble(self, content: str, timestamp: str, is_user: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("bubbleFrame")
        frame.setMaximumWidth(960)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        text = QLabel(content)
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; line-height: 1.6;")
        layout.addWidget(text)

        time_label = QLabel(timestamp)
        time_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(time_label)

        if is_user:
            bg = COLORS['user_bubble']
            radius = "border-radius: 16px 16px 4px 16px;"
        else:
            bg = COLORS['agent_bubble']
            radius = "border-radius: 16px 16px 16px 4px;"

        frame.setStyleSheet(f"""
            #bubbleFrame {{
                background-color: {bg};
                {radius}
            }}
        """)

        return frame


# ==============================================================================
# TransferConfirmBubble — 转人工确认气泡
# ==============================================================================
TRANSFER_CONFIRM_TEXT = "这条消息需人工回复"
TRANSFER_RESOLVED_TEXT = "消息已在商家后台处理"


class TransferConfirmBubble(QFrame):
    """转人工确认消息气泡，包含确认按钮"""
    confirmed = pyqtSignal()

    def __init__(self, content: str, timestamp: str = "", parent=None):
        super().__init__(parent)
        self._content = content
        self._timestamp = timestamp
        self._confirmed = (content == TRANSFER_RESOLVED_TEXT)
        self.setupUI()

    def setupUI(self):
        self.setObjectName("transferBubble")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(15, 6, 6, 15)
        outer.addStretch(1)

        frame = QFrame()
        frame.setObjectName("transferBubbleFrame")
        frame.setMaximumWidth(960)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        text = QLabel(self._content)
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; line-height: 1.6;")
        layout.addWidget(text)

        if not self._confirmed:
            confirm_btn = PushButton("确认已处理")
            confirm_btn.setStyleSheet(f"""
                PushButton {{
                    background-color: {COLORS['accent_green']};
                    color: {COLORS['text_primary']};
                    border-radius: 8px;
                    padding: 6px 20px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                PushButton:hover {{
                    background-color: #9cc89d;
                }}
            """)
            confirm_btn.clicked.connect(self.confirmed.emit)
            layout.addWidget(confirm_btn, 0, Qt.AlignmentFlag.AlignRight)

        time_label = QLabel(self._timestamp)
        time_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(time_label)

        bg = "#fff3e0" if not self._confirmed else COLORS['agent_bubble']
        frame.setStyleSheet(f"""
            #transferBubbleFrame {{
                background-color: {bg};
                border-radius: 16px 16px 16px 4px;
                border: 1px solid {COLORS['agent_border']};
            }}
        """)

        outer.addWidget(frame, 0)
        outer.addSpacing(10)

        avatar = AvatarWidget('assistant')
        outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)


# ==============================================================================
# 视图切换动画辅助
# ==============================================================================
def _animate_switch(stack: QStackedWidget, target_index: int, direction: int = 1):
    """direction: 1=前进(右→左), -1=后退(左→右)"""
    if stack.currentIndex() == target_index:
        return

    old_widget = stack.currentWidget()
    new_widget = stack.widget(target_index)

    if old_widget is None or new_widget is None:
        stack.setCurrentIndex(target_index)
        return

    duration = 220  # ms

    # 新视图初始状态
    new_opacity = QGraphicsOpacityEffect()
    new_widget.setGraphicsEffect(new_opacity)
    new_opacity.setOpacity(0.0)

    offset_x = 30 if direction > 0 else -30  # 前进时从右侧滑入，后退时从左侧滑入
    new_widget.move(new_widget.x() + offset_x, new_widget.y())

    stack.setCurrentIndex(target_index)

    # 新视图动画
    anim_opacity = QPropertyAnimation(new_opacity, b"opacity")
    anim_opacity.setStartValue(0.0)
    anim_opacity.setEndValue(1.0)
    anim_opacity.setDuration(duration)
    anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)

    anim_pos = QPropertyAnimation(new_widget, b"pos")
    target_pos = new_widget.pos()
    new_widget.move(target_pos.x() - offset_x, target_pos.y())
    anim_pos.setStartValue(QPoint(target_pos.x() - offset_x, target_pos.y()))
    anim_pos.setEndValue(target_pos)
    anim_pos.setDuration(duration)
    anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

    group = QParallelAnimationGroup()
    group.addAnimation(anim_opacity)
    group.addAnimation(anim_pos)
    group.start()

    # 动画结束后清理
    def _cleanup():
        new_widget.setGraphicsEffect(None)
        new_widget.move(target_pos)
    group.finished.connect(_cleanup)
    # 防止被回收
    stack._anim_group = group


# ==============================================================================
# 主页面
# ==============================================================================
class SessionManagementWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._loaded_once = False
        self._shops_cache = {}
        self._current_shop_id = None
        self._current_session_id = None
        self.setObjectName("SessionPage")
        self.setupUI()
        QTimer.singleShot(300, self._maybeLoadOnShow)

    def showEvent(self, event):
        super().showEvent(event)
        self._maybeLoadOnShow()

    def _maybeLoadOnShow(self):
        if not self._loaded_once and self.isVisible():
            self._loaded_once = True
            self._load_data()

    # ===== 构建 UI =====

    def setupUI(self):
        self.setStyleSheet(STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(0)

        # Header
        header = self._build_header()
        main_layout.addWidget(header)
        main_layout.addSpacing(16)

        # 双栏主体
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)

        left = self._build_left_panel()
        body_layout.addWidget(left)

        right = self._build_right_panel()
        body_layout.addWidget(right, 1)

        main_layout.addWidget(body, 1)

    def _build_header(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 0, 8, 0)

        title = SubtitleLabel("会话管理")
        title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 20px;")
        layout.addWidget(title)
        layout.addStretch()

        self.stats_label = CaptionLabel("共 0 个会话")
        self.stats_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self.stats_label)
        layout.addSpacing(12)

        refresh_btn = PushButton(FIF.SYNC, "刷新")
        refresh_btn.clicked.connect(self._load_data)
        layout.addWidget(refresh_btn)

        return widget

    def _build_left_panel(self):
        frame = QFrame()
        frame.setObjectName("leftPanel")
        frame.setFixedWidth(320)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(8)

        panel_title = SubtitleLabel("店铺列表")
        panel_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; padding: 0 4px;")
        layout.addWidget(panel_title)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("shopScroll")

        self.shop_container = QWidget()
        self.shop_layout = QVBoxLayout(self.shop_container)
        self.shop_layout.setContentsMargins(4, 4, 4, 4)
        self.shop_layout.setSpacing(6)
        self.shop_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.shop_container)
        layout.addWidget(scroll, 1)

        return frame

    def _build_right_panel(self):
        frame = QFrame()
        frame.setObjectName("rightPanel")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.right_stack = QStackedWidget()
        self.right_stack.setObjectName("rightStack")

        # 0: 占位页
        self.right_stack.addWidget(self._build_placeholder())
        # 1: 会话列表页
        self.right_stack.addWidget(self._build_conv_list_page())
        # 2: 聊天详情页
        self.right_stack.addWidget(self._build_chat_detail_page())

        layout.addWidget(self.right_stack)
        return frame

    def _build_placeholder(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel("💬")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)
        layout.addSpacing(12)

        hint = CaptionLabel("请从左侧选择一个店铺查看会话")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 15px;")
        layout.addWidget(hint)

        return page

    def _build_conv_list_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 顶部返回栏
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.conv_title = SubtitleLabel("会话列表")
        self.conv_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 18px;")
        top_layout.addWidget(self.conv_title)
        top_layout.addStretch()

        back_btn = PushButton(FIF.LEFT_ARROW, "返回店铺列表")
        back_btn.clicked.connect(lambda: _animate_switch(self.right_stack, 0, -1))
        top_layout.addWidget(back_btn)
        layout.addWidget(top)

        # 分隔线
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {COLORS['divider']};")
        layout.addWidget(divider)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)

        self.conv_container = QWidget()
        self.conv_layout = QVBoxLayout(self.conv_container)
        self.conv_layout.setContentsMargins(4, 8, 4, 8)
        self.conv_layout.setSpacing(8)
        self.conv_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.conv_container)
        layout.addWidget(scroll, 1)

        return page

    def _build_chat_detail_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 顶部控制栏
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_title = SubtitleLabel("聊天详情")
        self.chat_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 18px;")
        top_layout.addWidget(self.chat_title)
        top_layout.addStretch()

        back_conv_btn = PushButton(FIF.LEFT_ARROW, "返回会话列表")
        back_conv_btn.clicked.connect(lambda: _animate_switch(self.right_stack, 1, -1))
        top_layout.addWidget(back_conv_btn)

        delete_btn = PushButton(FIF.DELETE, "删除会话")
        delete_btn.clicked.connect(self._delete_current_session)
        top_layout.addWidget(delete_btn)
        layout.addWidget(top)

        # 分隔线
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {COLORS['divider']};")
        layout.addWidget(divider)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("chatScroll")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 12, 16, 24)
        self.chat_layout.setSpacing(0)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.chat_container)
        layout.addWidget(scroll, 1)

        return page

    # ===== 数据加载 =====

    def _load_data(self):
        self._clear_shop_list()
        self._shops_cache = {}

        try:
            from database.db_manager import db_manager
            mgr = _get_session_manager()
            session_shops = {s["shop_id"]: s for s in mgr.get_all_session_shops()}

            channels = db_manager.get_all_channels()
            for channel in channels:
                shops = db_manager.get_shops_by_channel(channel["channel_name"])
                for shop in shops:
                    sid = shop["shop_id"]
                    shop_name = shop.get("shop_name", "")
                    shop_sessions = mgr.get_sessions_by_shop(sid) if sid in session_shops else []
                    session_count = len(shop_sessions)
                    error_count = sum(1 for s in shop_sessions if s.get("is_error"))
                    transfer_count = sum(1 for s in shop_sessions if s.get("needs_human"))
                    self._shops_cache[sid] = {
                        "shop_name": shop_name,
                        "channel_name": channel["channel_name"],
                    }
                    card = ShopCard(sid, shop_name, session_count, error_count, transfer_count)
                    card.shop_selected.connect(self._on_shop_selected)
                    self.shop_layout.addWidget(card)

            for sid, sinfo in session_shops.items():
                if sid not in self._shops_cache:
                    shop_sessions = mgr.get_sessions_by_shop(sid)
                    error_count = sum(1 for s in shop_sessions if s.get("is_error"))
                    transfer_count = sum(1 for s in shop_sessions if s.get("needs_human"))
                    self._shops_cache[sid] = {"shop_name": "", "channel_name": sinfo.get("channel_type", "")}
                    card = ShopCard(sid, "", len(shop_sessions), error_count, transfer_count)
                    card.shop_selected.connect(self._on_shop_selected)
                    self.shop_layout.addWidget(card)

            total = sum(
                len(_get_session_manager().get_sessions_by_shop(sid))
                for sid in self._shops_cache
            )
            self.stats_label.setText(f"共 {total} 个会话")

        except Exception as e:
            logger.error(f"加载会话数据失败: {e}")

    def _clear_shop_list(self):
        while self.shop_layout.count():
            item = self.shop_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_conv_list(self):
        while self.conv_layout.count():
            item = self.conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ===== 交互逻辑 =====

    def _on_shop_selected(self, shop_id: str):
        self._current_shop_id = shop_id
        shop_info = self._shops_cache.get(shop_id, {})
        shop_name = shop_info.get("shop_name", "") or f"店铺 {shop_id}"
        self.conv_title.setText(f"「{shop_name}」的会话")

        # 更新选中状态
        for i in range(self.shop_layout.count()):
            w = self.shop_layout.itemAt(i).widget()
            if isinstance(w, ShopCard):
                w.set_selected(w._shop_id == shop_id)

        self._load_sessions_into_conv_layout(shop_id)
        _animate_switch(self.right_stack, 1, 1)
        self._current_session_id = None

    def _on_session_selected(self, session_id: str):
        self._current_session_id = session_id
        self.chat_title.setText(f"会话详情: {session_id}")
        self._load_messages_into_chat_layout(session_id)
        _animate_switch(self.right_stack, 2, 1)

    # ===== 实时刷新辅助方法 =====

    def _load_messages_into_chat_layout(self, session_id: str):
        """加载指定会话的消息到聊天区域"""
        self._clear_chat()
        try:
            mgr = _get_session_manager()
            messages = mgr.get_history(session_id)
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "") or ""
                ts = msg.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                        ts = dt.strftime("%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        pass

                # 转人工确认消息使用特殊气泡
                if role == "assistant" and content in (TRANSFER_CONFIRM_TEXT, TRANSFER_RESOLVED_TEXT):
                    confirm_bubble = TransferConfirmBubble(content, ts)
                    if content == TRANSFER_CONFIRM_TEXT:
                        confirm_bubble.confirmed.connect(
                            lambda sid=session_id: self._handle_transfer_confirmed(sid)
                        )
                    self.chat_layout.addWidget(confirm_bubble)
                else:
                    bubble = MessageBubble(role, content, ts)
                    self.chat_layout.addWidget(bubble)

            if not messages:
                empty = CaptionLabel("暂无消息记录")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 40px;")
                self.chat_layout.addWidget(empty)
        except Exception as e:
            logger.error(f"加载聊天消息失败: {e}")

    def _handle_transfer_confirmed(self, session_id: str):
        """处理转人工确认：取消标记 + 更新消息文本"""
        try:
            mgr = _get_session_manager()
            # 取消人工处理标记
            mgr.unmark_session_needs_human(session_id)
            # 更新消息文本
            mgr.update_message_content(session_id, TRANSFER_CONFIRM_TEXT, TRANSFER_RESOLVED_TEXT)
            # 刷新当前聊天视图
            self._load_messages_into_chat_layout(session_id)
            QTimer.singleShot(100, self._scroll_chat_to_bottom)
            # 刷新当前店铺的会话列表和卡片计数
            if self._current_shop_id:
                self._load_sessions_into_conv_layout(self._current_shop_id)
                self._update_shop_card_counts(self._current_shop_id)
        except Exception as e:
            logger.error(f"处理转人工确认失败: {e}")

    def _load_sessions_into_conv_layout(self, shop_id: str):
        """加载指定店铺的会话列表到对话区域"""
        self._clear_conv_list()
        try:
            mgr = _get_session_manager()
            sessions = mgr.get_sessions_by_shop(shop_id)
            for sess in sessions:
                card = ConversationCard(sess)
                card.session_selected.connect(self._on_session_selected)
                self.conv_layout.addWidget(card)

            if not sessions:
                empty = CaptionLabel("暂无会话记录")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 40px;")
                self.conv_layout.addWidget(empty)
        except Exception as e:
            logger.error(f"加载会话列表失败: {e}")

    def _update_shop_card_counts(self, target_shop_id: str):
        """轻量更新单个店铺卡片的会话/转人工/错误计数"""
        try:
            mgr = _get_session_manager()
            for i in range(self.shop_layout.count()):
                w = self.shop_layout.itemAt(i).widget()
                if isinstance(w, ShopCard) and w._shop_id == target_shop_id:
                    sessions = mgr.get_sessions_by_shop(target_shop_id)
                    session_count = len(sessions)
                    error_count = sum(1 for s in sessions if s.get("is_error"))
                    transfer_count = sum(1 for s in sessions if s.get("needs_human"))
                    w.update_counts(session_count, error_count, transfer_count)
                    break

            total = sum(
                len(mgr.get_sessions_by_shop(sid))
                for sid in self._shops_cache
            )
            self.stats_label.setText(f"共 {total} 个会话")
        except Exception as e:
            logger.error(f"更新店铺卡片计数失败: {e}")

    def _scroll_chat_to_bottom(self):
        """滚动聊天区域到底部"""
        scroll = self.findChild(QScrollArea, "chatScroll")
        if scroll:
            vsb = scroll.verticalScrollBar()
            vsb.setValue(vsb.maximum())

    def _on_message_updated(self, session_id: str, shop_id: str):
        """收到新消息信号后的智能局部刷新"""
        try:
            current_index = self.right_stack.currentIndex()

            if current_index == 2 and self._current_session_id == session_id:
                self._load_messages_into_chat_layout(session_id)
                QTimer.singleShot(100, self._scroll_chat_to_bottom)

            if current_index == 1 and self._current_shop_id == shop_id:
                self._load_sessions_into_conv_layout(shop_id)

            self._update_shop_card_counts(shop_id)
        except Exception as e:
            logger.error(f"处理会话更新失败: {e}")

    # ===== 删除操作 =====

    def _delete_current_session(self):
        if not self._current_session_id:
            return

        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"确定要删除会话「{self._current_session_id}」及其所有消息吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                mgr = _get_session_manager()
                if mgr.delete_session(self._current_session_id):
                    self._clear_chat()
                    self._current_session_id = None
                    self.chat_title.setText("会话详情")
                    self._on_shop_selected(self._current_shop_id)
                    self._load_data()
                else:
                    QMessageBox.warning(self, "删除失败", "删除会话失败，请稍后重试。")
            except Exception as e:
                logger.error(f"删除会话失败: {e}")
                QMessageBox.warning(self, "删除失败", f"删除会话时出错: {e}")
