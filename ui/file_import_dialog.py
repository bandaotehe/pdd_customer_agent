"""
文件导入对话框 — 支持 TXT / Excel 文件导入知识库，含分段控制与预览
支持两种模式：客服知识 (customer_service) 和 产品知识 (product)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QLineEdit, QPushButton, QFileDialog, QCheckBox, QScrollArea,
    QFrame, QComboBox, QGroupBox, QGridLayout,
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    InfoBar, InfoBarPosition,
)

from utils.logger_loguru import get_logger

logger = get_logger("FileImportDialog")

DEFAULT_TAGS = ["物流", "售后", "支付", "商品规格", "优惠券", "会员", "发货时间", "退换货"]

SEGMENT_MODES = {
    "按段落": "\n\n",
    "按换行": "\n",
    "按句号": "。",
    "自定义分隔符": "__custom__",
}


def _parse_txt(content: str, delimiter: str) -> list[dict[str, str]]:
    if delimiter == "__custom__":
        delimiter = "\n\n"

    parts = [p.strip() for p in content.split(delimiter) if p.strip()]
    if not parts:
        return []

    entries = []
    for part in parts:
        lines = part.strip().split("\n", 1)
        if len(lines) == 1:
            entries.append({"title": lines[0].strip(), "content": lines[0].strip()})
        else:
            entries.append({"title": lines[0].strip(), "content": part.strip()})
    return entries


def _parse_excel_with_mapping(
    filepath: str, col_a_idx: int, col_b_idx: int, col_c_idx: int | None,
) -> list[dict[str, str]]:
    import pandas as pd
    df = pd.read_excel(filepath, header=0, dtype=str)
    df = df.fillna("")
    all_cols = [str(c) for c in df.columns]

    entries = []
    for _, row in df.iterrows():
        values = [str(v).strip() for v in row.tolist()]
        a = values[col_a_idx] if col_a_idx < len(values) else ""
        b = values[col_b_idx] if col_b_idx < len(values) else ""
        c = values[col_c_idx] if col_c_idx is not None and col_c_idx < len(values) else ""

        if not b.strip():
            continue

        entries.append({"col_a": a, "col_b": b, "col_c": c})
    return entries


class PreviewRow(QFrame):
    """预览条目行"""

    def __init__(self, index: int, label_a: str, label_b: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self.label_a = label_a
        self.label_b = label_b

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        layout.addWidget(self.checkbox)

        preview_b = label_b[:80] + ("..." if len(label_b) > 80 else "")
        text = f"<b>{label_a}</b>&nbsp;&nbsp;—&nbsp;&nbsp;<span style='color:#666;'>{preview_b}</span>"
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label, 1)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


class FileImportDialog(QDialog):
    """文件导入对话框

    mode: "customer_service" — 标题/内容/标签列映射
          "product" — 商品ID/商品名称/价格/商品知识列映射
    """

    def __init__(self, parent: QWidget | None = None, mode: str = "customer_service"):
        super().__init__(parent)
        self._mode = mode

        if mode == "product":
            self.setWindowTitle("产品导入")
        else:
            self.setWindowTitle("文件导入")

        self.setMinimumSize(700, 560)
        self.resize(750, 600)

        self._filepath: str = ""
        self._parsed_entries: list[dict[str, str]] = []
        self._preview_rows: list[PreviewRow] = []
        self._file_type: str = ""

        self._build_ui()

    # ── Public API ──

    def get_selected_entries(self) -> list[dict[str, str]]:
        """客服知识模式：返回 {title, content} 列表"""
        result = []
        for row in self._preview_rows:
            if row.is_checked():
                result.append({"title": row.label_a, "content": row.label_b})
        return result

    def get_selected_product_entries(self) -> list[dict[str, str]]:
        """产品模式：返回 {goods_id, goods_name, price, extracted_content} 列表"""
        result = []
        for i, row in enumerate(self._preview_rows):
            if row.is_checked():
                entry = self._parsed_entries[i]
                result.append({
                    "goods_id": entry.get("col_a", ""),
                    "goods_name": entry.get("col_b", ""),
                    "price": entry.get("col_c", ""),
                    "extracted_content": entry.get("col_b", ""),
                })
        return result

    def get_tags(self) -> str:
        tags = [cb.text() for cb in self._tag_checkboxes if cb.isChecked()]
        custom = self._custom_tag_input.text().strip()
        if custom:
            tags.append(custom)
        return ",".join(tags)

    # ── UI ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel(self.windowTitle()))

        # 文件选择
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self._file_input = QLineEdit()
        self._file_input.setPlaceholderText("选择 .txt / .xlsx / .xls 文件...")
        self._file_input.setReadOnly(True)
        file_row.addWidget(self._file_input, 1)
        select_btn = PushButton("选择文件")
        select_btn.clicked.connect(self._on_select_file)
        file_row.addWidget(select_btn)
        layout.addLayout(file_row)

        # 分段设置
        self._segment_group = QGroupBox("分段设置")
        segment_layout = QVBoxLayout(self._segment_group)
        segment_layout.setSpacing(8)

        self._txt_segment_row = QWidget()
        txt_seg_layout = QHBoxLayout(self._txt_segment_row)
        txt_seg_layout.setContentsMargins(0, 0, 0, 0)
        txt_seg_layout.addWidget(QLabel("分段方式:"))
        self._segment_combo = QComboBox()
        self._segment_combo.addItems(list(SEGMENT_MODES.keys()))
        self._segment_combo.currentTextChanged.connect(self._on_segment_mode_changed)
        txt_seg_layout.addWidget(self._segment_combo)
        txt_seg_layout.addStretch()
        segment_layout.addWidget(self._txt_segment_row)

        self._custom_delim_row = QWidget()
        custom_layout = QHBoxLayout(self._custom_delim_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.addWidget(QLabel("自定义分隔符:"))
        self._custom_delim_input = QLineEdit()
        self._custom_delim_input.setPlaceholderText("输入分隔符，如 | 或 ；")
        self._custom_delim_input.setMaximumWidth(200)
        custom_layout.addWidget(self._custom_delim_input)
        custom_layout.addStretch()
        self._custom_delim_row.setVisible(False)
        segment_layout.addWidget(self._custom_delim_row)

        # Excel 列映射（标签随 mode 变化）
        self._excel_map_row = QWidget()
        excel_map_layout = QGridLayout(self._excel_map_row)
        excel_map_layout.setContentsMargins(0, 0, 0, 0)
        excel_map_layout.setSpacing(8)

        if self._mode == "product":
            col_a_label = "商品ID列:"
            col_b_label = "商品名称列:"
            col_c_label = "价格列:"
        else:
            col_a_label = "标题列:"
            col_b_label = "内容列:"
            col_c_label = "标签列(可选):"

        excel_map_layout.addWidget(QLabel(col_a_label), 0, 0)
        self._col_a_combo = QComboBox()
        excel_map_layout.addWidget(self._col_a_combo, 0, 1)
        excel_map_layout.addWidget(QLabel(col_b_label), 0, 2)
        self._col_b_combo = QComboBox()
        excel_map_layout.addWidget(self._col_b_combo, 0, 3)
        excel_map_layout.addWidget(QLabel(col_c_label), 0, 4)
        self._col_c_combo = QComboBox()
        excel_map_layout.addWidget(self._col_c_combo, 0, 5)

        self._excel_map_row.setVisible(False)
        segment_layout.addWidget(self._excel_map_row)
        self._segment_group.setVisible(False)
        layout.addWidget(self._segment_group)

        # 标签选择（产品模式隐藏）
        self._tag_group = QGroupBox("标签 (可选)")
        tag_layout = QVBoxLayout(self._tag_group)
        self._tag_checkboxes: list[QCheckBox] = []
        tag_check_row = QHBoxLayout()
        tag_check_row.setSpacing(12)
        for tag in DEFAULT_TAGS:
            cb = QCheckBox(tag)
            self._tag_checkboxes.append(cb)
            tag_check_row.addWidget(cb)
        tag_check_row.addStretch()
        tag_layout.addLayout(tag_check_row)

        custom_tag_row = QHBoxLayout()
        custom_tag_row.addWidget(QLabel("自定义标签:"))
        self._custom_tag_input = QLineEdit()
        self._custom_tag_input.setPlaceholderText("输入自定义标签")
        self._custom_tag_input.setMaximumWidth(250)
        custom_tag_row.addWidget(self._custom_tag_input)
        custom_tag_row.addStretch()
        tag_layout.addLayout(custom_tag_row)

        layout.addWidget(self._tag_group)

        if self._mode == "product":
            self._tag_group.setVisible(False)

        # 预览 & 解析按钮
        preview_header = QHBoxLayout()
        self._preview_count_label = BodyLabel("预览 (共 0 条)")
        preview_header.addWidget(self._preview_count_label)
        preview_header.addStretch()

        self._parse_btn = PrimaryPushButton("解析预览")
        self._parse_btn.clicked.connect(self._on_parse)
        self._parse_btn.setEnabled(False)
        preview_header.addWidget(self._parse_btn)
        layout.addLayout(preview_header)

        # 预览区域
        self._preview_scroll = QScrollArea()
        self._preview_scroll.setWidgetResizable(True)
        self._preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._preview_widget = QWidget()
        self._preview_layout = QVBoxLayout(self._preview_widget)
        self._preview_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_layout.setSpacing(2)
        self._preview_layout.addStretch()
        self._preview_scroll.setWidget(self._preview_widget)
        self._preview_scroll.setMinimumHeight(150)
        self._preview_scroll.setStyleSheet(
            "QScrollArea { background: #fafafa; border: 1px solid #ddd; border-radius: 6px; }"
        )
        layout.addWidget(self._preview_scroll, 1)

        # 底部按钮
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)

        self._import_btn = PrimaryPushButton("导入")
        self._import_btn.clicked.connect(self._on_import)
        self._import_btn.setEnabled(False)
        bottom_row.addWidget(self._import_btn)
        layout.addLayout(bottom_row)

    # ── 事件处理 ──

    def _on_select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "",
            "知识文件 (*.txt *.xlsx *.xls);;文本文件 (*.txt);;Excel 文件 (*.xlsx *.xls)",
        )
        if not filepath:
            return

        self._filepath = filepath
        self._file_input.setText(filepath)

        ext = filepath.rsplit(".", 1)[-1].lower()
        if ext in ("xlsx", "xls"):
            self._file_type = "excel"
            self._setup_excel_columns()
            self._txt_segment_row.setVisible(False)
            self._custom_delim_row.setVisible(False)
            self._excel_map_row.setVisible(True)
        else:
            self._file_type = "txt"
            self._txt_segment_row.setVisible(True)
            self._excel_map_row.setVisible(False)
            self._on_segment_mode_changed(self._segment_combo.currentText())

        self._segment_group.setVisible(True)
        self._parse_btn.setEnabled(True)
        self._clear_preview()

    def _setup_excel_columns(self):
        try:
            import pandas as pd
            df = pd.read_excel(self._filepath, header=0, dtype=str)
            cols = [str(c) for c in df.columns]
        except Exception:
            cols = []

        for combo in (self._col_a_combo, self._col_b_combo):
            combo.clear()
            combo.addItems(cols)

        self._col_c_combo.clear()
        if self._mode == "product":
            self._col_c_combo.addItems(cols)
        else:
            self._col_c_combo.addItem("(不使用)", "__none__")
            self._col_c_combo.addItems(cols)

        if len(cols) >= 2:
            self._col_a_combo.setCurrentIndex(0)
            self._col_b_combo.setCurrentIndex(1)

    def _on_segment_mode_changed(self, mode: str):
        self._custom_delim_row.setVisible(mode == "自定义分隔符")

    def _clear_preview(self):
        while self._preview_layout.count() > 1:
            item = self._preview_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._preview_rows.clear()
        self._preview_count_label.setText("预览 (共 0 条)")
        self._import_btn.setEnabled(False)

    def _on_parse(self):
        try:
            if self._file_type == "txt":
                self._parse_txt_file()
            else:
                self._parse_excel_file()
        except Exception as e:
            logger.exception("文件解析失败")
            InfoBar.error(
                title="解析失败", content=f"文件解析出错: {e}",
                orient=Qt.Orientation.Vertical, isClosable=True,
                duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self,
            )

    def _parse_txt_file(self):
        mode = self._segment_combo.currentText()
        delimiter = SEGMENT_MODES.get(mode, "\n\n")

        if delimiter == "__custom__":
            delimiter = self._custom_delim_input.text()
            if not delimiter:
                InfoBar.warning(
                    title="提示", content="请输入自定义分隔符",
                    orient=Qt.Orientation.Vertical, isClosable=True,
                    duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self,
                )
                return

        with open(self._filepath, "r", encoding="utf-8") as f:
            content = f.read()

        raw = _parse_txt(content, delimiter)
        if self._mode == "product":

            self._parsed_entries = []
            for entry in raw:
                self._parsed_entries.append({
                    "col_a": entry["title"],
                    "col_b": entry["content"],
                    "col_c": "",
                })
        else:
            self._parsed_entries = [
                {"col_a": e["title"], "col_b": e["content"], "col_c": ""}
                for e in raw
            ]
        self._show_preview()

    def _parse_excel_file(self):
        col_a = self._col_a_combo.currentText()
        col_b = self._col_b_combo.currentText()
        col_c = self._col_c_combo.currentText()

        if not col_a or not col_b:
            InfoBar.warning(
                title="提示", content="请选择必填列",
                orient=Qt.Orientation.Vertical, isClosable=True,
                duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self,
            )
            return

        import pandas as pd
        df = pd.read_excel(self._filepath, header=0, dtype=str)
        df = df.fillna("")
        all_cols = [str(c) for c in df.columns]

        col_a_idx = all_cols.index(col_a) if col_a in all_cols else 0
        col_b_idx = all_cols.index(col_b) if col_b in all_cols else 1
        col_c_idx = all_cols.index(col_c) if col_c in all_cols and col_c != "__none__" else None

        if self._mode == "product":
            self._parsed_entries = []
            for _, row in df.iterrows():
                values = [str(v).strip() for v in row.tolist()]
                gid = values[col_a_idx] if col_a_idx < len(values) else ""
                name = values[col_b_idx] if col_b_idx < len(values) else ""
                price = values[col_c_idx] if col_c_idx is not None and col_c_idx < len(values) else ""
                if not name.strip():
                    continue
                self._parsed_entries.append({"col_a": gid, "col_b": name, "col_c": price})
        else:
            self._parsed_entries = _parse_excel_with_mapping(
                self._filepath, col_a_idx, col_b_idx, col_c_idx,
            )

        self._show_preview()

    def _show_preview(self):
        self._clear_preview()
        if not self._parsed_entries:
            self._preview_count_label.setText("预览 (共 0 条 — 文件为空)")
            return

        for i, entry in enumerate(self._parsed_entries):
            row = PreviewRow(i, entry["col_a"], entry["col_b"])
            self._preview_rows.append(row)
            self._preview_layout.insertWidget(self._preview_layout.count() - 1, row)

        n = len(self._parsed_entries)
        self._preview_count_label.setText(f"预览 (共 {n} 条)")
        self._import_btn.setEnabled(True)
        self._import_btn.setText(f"导入 ({n} 条)")

    def _on_import(self):
        selected = False
        for row in self._preview_rows:
            if row.is_checked():
                selected = True
                break
        if not selected:
            InfoBar.warning(
                title="提示", content="没有选中任何条目",
                orient=Qt.Orientation.Vertical, isClosable=True,
                duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self,
            )
            return
        self.accept()
