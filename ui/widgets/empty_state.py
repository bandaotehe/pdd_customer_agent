"""
空状态占位组件

统一所有页面无数据时的显示样式 — 居中图标 + 提示文字 + 可选副标题。
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import CaptionLabel, BodyLabel
from ui.theme import COLORS


class EmptyStateWidget(QWidget):
    """空状态占位组件 — 居中大图标 + 提示文字"""

    def __init__(self, icon: str = "", text: str = "", sub_text: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(f"font-size: 48px; color: {COLORS['text_disabled']};")
            layout.addWidget(icon_label)

        if text:
            text_label = BodyLabel(text)
            text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 15px;")
            layout.addWidget(text_label)

        if sub_text:
            sub_label = CaptionLabel(sub_text)
            sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_label.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 12px;")
            layout.addWidget(sub_label)

        self.setMinimumHeight(200)
