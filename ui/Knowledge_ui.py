"""
知识库管理UI模块
==============

提供产品知识、客服知识、自定义知识库和关键词管理界面，包含：
- 顶部店铺选择器
- 四个标签页：产品知识 / 客服知识 / 自定义知识库 / 关键词管理
- 自动同步产品知识（拼多多API + LLM提取）
- 客服知识人工添加/编辑/删除
"""
from __future__ import annotations
import asyncio
import os
from typing import TYPE_CHECKING, Optional, List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QMessageBox, QDialog, QDialogButtonBox,
    QLineEdit, QTextEdit, QCheckBox, QProgressBar, QFrame, QFileDialog,
    QSpinBox, QGroupBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from qfluentwidgets import (
    PrimaryPushButton, PushButton,
    InfoBar, InfoBarPosition, TableWidget, SegmentedWidget,
    ComboBox, FluentIcon as FIF,
)

from core.di_container import container
from database.knowledge_service import KnowledgeService
from ui.theme import COLORS, SPACING, scrollbar_style
from database.product_sync import ProductSyncService, SyncProgress
from database.models import ProductKnowledge, CustomerServiceKnowledge, CustomKnowledge, Shop
from utils.logger_loguru import get_logger

if TYPE_CHECKING:
    from database.knowledge_service import KnowledgeService

logger = get_logger("KnowledgeUI")


class SyncWorker(QThread):
    """同步工作线程"""
    progress_updated = pyqtSignal(int, int, int, str, str)  # current, total, success, current_name, phase
    sync_finished = pyqtSignal(int, int, bool)  # success, failed, cancelled

    def __init__(
        self,
        shop_db_id: int,
        pdd_shop_id: str,
        user_id: str,
        is_full_sync: bool,
        product_sync: ProductSyncService,
        parent=None,
    ):
        super().__init__(parent)
        self.shop_db_id = shop_db_id
        self.pdd_shop_id = pdd_shop_id
        self.user_id = user_id
        self.is_full_sync = is_full_sync
        self.product_sync = product_sync
        self._cancelled = False

    def run(self):
        """运行同步"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def progress_callback(progress: SyncProgress):
            self.progress_updated.emit(
                progress.current,
                progress.total,
                progress.success,
                progress.current_goods_name,
                progress.phase,
            )

        result = loop.run_until_complete(
            self.product_sync.sync_shop(
                shop_id=int(self.pdd_shop_id),
                shop_db_id=self.shop_db_id,
                user_id=self.user_id,
                is_full_sync=self.is_full_sync,
                progress_callback=progress_callback,
            )
        )

        loop.close()
        self.sync_finished.emit(result.success, result.failed, result.cancelled)


class ProductDetailDialog(QDialog):
    """产品知识详情对话框，支持编辑"""

    def __init__(self, product: ProductKnowledge, parent=None):
        super().__init__(parent)
        self.product = product
        self._new_image_path: str = ""
        self.setWindowTitle("产品知识详情 - " + (product.goods_name or ""))
        self.resize(700, 550)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("商品名称:"))
        self.name_edit = QLineEdit(self.product.goods_name)
        layout.addWidget(self.name_edit)

        r_price = QHBoxLayout()
        r_price.addWidget(QLabel("价格:"))
        self.price_edit = QLineEdit(self.product.price or "")
        r_price.addWidget(self.price_edit)
        layout.addLayout(r_price)

        r_img = QHBoxLayout()
        r_img.addWidget(QLabel("图片:"))
        current = self.product.image_path or ""
        self.image_label = QLabel(os.path.basename(current) if current else "未上传")
        self.image_label.setStyleSheet(f"color: {COLORS['text_disabled']};" if not current else f"color: {COLORS['kpi_green']};")
        r_img.addWidget(self.image_label, 1)
        self.image_btn = QPushButton("更换图片")
        self.image_btn.clicked.connect(self._on_select_image)
        r_img.addWidget(self.image_btn)
        layout.addLayout(r_img)

        layout.addWidget(QLabel("产品知识内容:"))
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(self.product.extracted_content or "")
        self.content_edit.setPlaceholderText("产品知识内容，例如：成分、功效、使用方法等")
        layout.addWidget(self.content_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_select_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if not filepath:
            return
        self.image_label.setText("处理中...")
        self.image_label.setStyleSheet(f"color: {COLORS['text_disabled']};")
        import shutil
        dest_dir = Path("temp") / "product_images"
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(filepath).suffix
        dest = dest_dir / f"{self.product.goods_name or 'product'}{ext}"
        shutil.copy2(filepath, dest)
        self._new_image_path = str(dest)
        from utils.oss_client import upload_to_oss
        upload_to_oss(filepath)
        self.image_label.setText(Path(filepath).name + " ✓")
        self.image_label.setStyleSheet(f"color: {COLORS['kpi_green']};")

    def get_data(self):
        """获取编辑后的数据"""
        return {
            "goods_name": self.name_edit.text().strip(),
            "price": self.price_edit.text().strip() or None,
            "extracted_content": self.content_edit.toPlainText().strip(),
            "image_path": self._new_image_path or None,
        }


class CsAddEditDialog(QDialog):
    """客服知识添加/编辑对话框"""

    def __init__(
        self,
        shop_id: int,
        existing: Optional[CustomerServiceKnowledge] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.shop_id = shop_id
        self.existing = existing
        self.default_tags = ["物流", "售后", "支付", "商品规格", "优惠券", "会员", "发货时间", "退换货"]
        self.setWindowTitle("添加客服知识" if not existing else "编辑客服知识")
        self.resize(650, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 标题
        self.title_label = QLabel("标题:")
        self.title_edit = QLineEdit()
        if self.existing:
            self.title_edit.setText(self.existing.title)
        layout.addWidget(self.title_label)
        layout.addWidget(self.title_edit)

        # 内容
        self.content_label = QLabel("内容:")
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("输入客服知识内容，例如：退换货政策说明...")
        if self.existing:
            self.content_edit.setText(self.existing.content)
        layout.addWidget(self.content_label)
        layout.addWidget(self.content_edit)

        # 标签 - 预设复选框
        self.tags_label = QLabel("选择标签 (可多选):")
        layout.addWidget(self.tags_label)

        self.tag_checkboxes: List[QCheckBox] = []
        existing_tags = []
        if self.existing and self.existing.tags:
            existing_tags = [t.strip() for t in self.existing.tags.split(',') if t.strip()]

        tags_frame = QFrame()
        tags_layout = QHBoxLayout(tags_frame)
        tags_layout.setSpacing(8)

        for tag in self.default_tags:
            cb = QCheckBox(tag)
            if tag in existing_tags:
                cb.setChecked(True)
            tags_layout.addWidget(cb)
            self.tag_checkboxes.append(cb)

        layout.addWidget(tags_frame)

        # 自定义标签
        self.custom_label = QLabel("自定义标签 (逗号分隔):")
        self.custom_edit = QLineEdit()
        if self.existing and self.existing.tags:
            # 已有标签中不在预设列表的合并到自定义
            existing_custom = [
                t for t in existing_tags
                if t not in self.default_tags
            ]
            if existing_custom:
                self.custom_edit.setText(','.join(existing_custom))
        layout.addWidget(self.custom_label)
        layout.addWidget(self.custom_edit)

        # 启用
        self.enabled_cb = QCheckBox("启用")
        self.enabled_cb.setChecked(True)
        if self.existing:
            self.enabled_cb.setChecked(self.existing.enabled)
        layout.addWidget(self.enabled_cb)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        """获取数据"""
        title = self.title_edit.text().strip()
        content = self.content_edit.toPlainText().strip()
        enabled = self.enabled_cb.isChecked()

        # 收集选中的预设标签
        selected_tags = [
            cb.text() for cb in self.tag_checkboxes
                if cb.isChecked()
        ]

        # 添加自定义标签
        custom = self.custom_edit.text().strip()
        if custom:
            selected_tags.extend([t.strip() for t in custom.split(',') if t.strip()])

        # 去重
        selected_tags = list(dict.fromkeys(selected_tags))
        tags_str = ','.join(selected_tags) if selected_tags else None

        return {
            "title": title,
            "content": content,
            "tags": tags_str,
            "enabled": enabled,
        }


class KnowledgeConfigDialog(QDialog):
    """知识库全局配置弹窗 — Embedding / Reranker / 混合检索参数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("知识库模型配置")
        self.resize(520, 380)
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Embedding
        emb_gb = QGroupBox("Embedding 模型")
        emb_layout = QVBoxLayout(emb_gb)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Provider:"))
        self.emb_provider = ComboBox()
        self.emb_provider.addItems(["openai", "local"])
        r1.addWidget(self.emb_provider)
        r1.addWidget(QLabel("Model:"))
        self.emb_model = QLineEdit()
        r1.addWidget(self.emb_model)
        emb_layout.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("API Key:"))
        self.emb_api_key = QLineEdit()
        self.emb_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        r2.addWidget(self.emb_api_key)
        r2.addWidget(QLabel("API Base:"))
        self.emb_api_base = QLineEdit()
        r2.addWidget(self.emb_api_base)
        emb_layout.addLayout(r2)
        layout.addWidget(emb_gb)

        # Reranker
        rerank_gb = QGroupBox("Reranker 重排序模型")
        rerank_layout = QVBoxLayout(rerank_gb)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Provider:"))
        self.rerank_provider = ComboBox()
        self.rerank_provider.addItems(["local", "api"])
        r3.addWidget(self.rerank_provider)
        r3.addWidget(QLabel("Model:"))
        self.rerank_model = QLineEdit()
        r3.addWidget(self.rerank_model)
        rerank_layout.addLayout(r3)
        layout.addWidget(rerank_gb)

        # Hybrid alpha + chunk params
        param_gb = QGroupBox("检索 & 分块参数")
        param_layout = QVBoxLayout(param_gb)
        r4 = QHBoxLayout()
        r4.addWidget(QLabel("混合检索权重 (0=B25, 1=向量):"))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_label = QLabel("0.50")
        self.alpha_slider.valueChanged.connect(lambda v: self.alpha_label.setText(f"{v/100:.2f}"))
        r4.addWidget(self.alpha_slider)
        r4.addWidget(self.alpha_label)
        param_layout.addLayout(r4)
        r5 = QHBoxLayout()
        r5.addWidget(QLabel("分块大小:"))
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(100, 2000)
        r5.addWidget(self.chunk_size_spin)
        r5.addWidget(QLabel("重叠:"))
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 500)
        r5.addWidget(self.chunk_overlap_spin)
        r5.addStretch()
        param_layout.addLayout(r5)
        layout.addWidget(param_gb)

        layout.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self):
        try:
            from config import get_config
            emb = get_config("knowledge_base.embedding", {})
            rerank = get_config("knowledge_base.reranker", {})
            alpha = get_config("knowledge_base.hybrid_search_alpha", 0.5)
            cs = get_config("knowledge_base.chunk_size", 500)
            co = get_config("knowledge_base.chunk_overlap", 50)

            idx = self.emb_provider.findText(emb.get("provider", "openai"))
            if idx >= 0: self.emb_provider.setCurrentIndex(idx)
            self.emb_model.setText(emb.get("model_name", ""))
            self.emb_api_key.setText(emb.get("api_key", ""))
            self.emb_api_base.setText(emb.get("api_base", ""))

            idx = self.rerank_provider.findText(rerank.get("provider", "local"))
            if idx >= 0: self.rerank_provider.setCurrentIndex(idx)
            self.rerank_model.setText(rerank.get("model_name", ""))

            self.alpha_slider.setValue(int(alpha * 100))
            self.chunk_size_spin.setValue(cs)
            self.chunk_overlap_spin.setValue(co)
        except Exception:
            pass

    def _save_and_accept(self):
        try:
            from config import config
            config.update({
                "knowledge_base": {
                    "embedding": {
                        "provider": self.emb_provider.currentText(),
                        "model_name": self.emb_model.text().strip(),
                        "api_key": self.emb_api_key.text().strip(),
                        "api_base": self.emb_api_base.text().strip(),
                        "dimension": 1536,
                    },
                    "reranker": {
                        "provider": self.rerank_provider.currentText(),
                        "model_name": self.rerank_model.text().strip(),
                    },
                    "hybrid_search_alpha": self.alpha_slider.value() / 100.0,
                    "chunk_size": self.chunk_size_spin.value(),
                    "chunk_overlap": self.chunk_overlap_spin.value(),
                }
            }, save=True)
            self.accept()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", str(e))


class ProductAddDialog(QDialog):
    """手动添加产品知识弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加产品知识")
        self.resize(550, 480)
        self._image_local_path: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("商品 ID:"))
        self.goods_id_edit = QLineEdit()
        self.goods_id_edit.setPlaceholderText("输入拼多多商品ID（数字）")
        r1.addWidget(self.goods_id_edit)
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("商品名称:"))
        self.goods_name_edit = QLineEdit()
        self.goods_name_edit.setPlaceholderText("如：维生素C片 100粒")
        r2.addWidget(self.goods_name_edit)
        layout.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("价格:"))
        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("如：29.9-39.9")
        r3.addWidget(self.price_edit)
        layout.addLayout(r3)

        r4 = QHBoxLayout()
        r4.addWidget(QLabel("说明书图片:"))
        self.image_label = QLabel("未选择")
        self.image_label.setStyleSheet(f"color: {COLORS['text_disabled']};")
        r4.addWidget(self.image_label, 1)
        self.image_btn = QPushButton("选择图片")
        self.image_btn.clicked.connect(self._on_select_image)
        r4.addWidget(self.image_btn)
        layout.addLayout(r4)

        layout.addWidget(QLabel("产品知识内容:"))
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("输入产品知识详情，例如：成分、功效、使用方法等。\n保存后自动分块并写入向量数据库。")
        layout.addWidget(self.content_edit)

        layout.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        goods_id_text = self.goods_id_edit.text().strip()
        goods_name = self.goods_name_edit.text().strip()
        if not goods_id_text or not goods_name:
            QMessageBox.warning(self, "提示", "商品ID和名称不能为空")
            return
        try:
            int(goods_id_text)
        except ValueError:
            QMessageBox.warning(self, "提示", "商品ID必须为数字")
            return
        self.accept()

    def _on_select_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择说明书图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if not filepath:
            return
        self.image_label.setText("处理中...")
        self.image_label.setStyleSheet(f"color: {COLORS['text_disabled']};")
        # 拷贝到本地 temp/product_images/
        import shutil
        dest_dir = Path("temp") / "product_images"
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(filepath).suffix
        dest = dest_dir / f"{self.goods_id_edit.text().strip() or 'product'}{ext}"
        shutil.copy2(filepath, dest)
        self._image_local_path = str(dest)
        # 异步上传到 OSS 备份
        from utils.oss_client import upload_to_oss
        upload_to_oss(filepath)
        self.image_label.setText(Path(filepath).name + " ✓")
        self.image_label.setStyleSheet(f"color: {COLORS['kpi_green']};")

    def get_data(self):
        return {
            "goods_id": int(self.goods_id_edit.text().strip()),
            "goods_name": self.goods_name_edit.text().strip(),
            "price": self.price_edit.text().strip() or None,
            "content": self.content_edit.toPlainText().strip() or None,
            "image_path": self._image_local_path or None,
        }


class KnowledgeUI(QWidget):
    """知识库管理主界面"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName('KnowledgeUI')
        self.resize(900, 700)

        # 从DI容器获取服务
        self.knowledge_service: KnowledgeService = container.get(KnowledgeService)
        self.product_sync = ProductSyncService(self.knowledge_service)

        # 自定义知识库服务（可选）
        self.custom_kb_service = None
        self.chunking_service = None
        self.vector_sync = None
        try:
            from services.custom_knowledge_service import CustomKnowledgeService
            from services.chunking_service import ChunkingService
            from services.vector_index_sync import VectorIndexSync
            self.custom_kb_service = container.get(CustomKnowledgeService)
            self.chunking_service = container.get(ChunkingService)
            self.vector_sync = container.get(VectorIndexSync)
        except Exception:
            pass

        # 当前选中的店铺
        self.current_shop_id: Optional[int] = None
        # 店铺缓存 {shop_id: shop_name}
        self._shop_cache: Dict[int, str] = {}

        # 懒加载标志：只在首次切换到对应标签页时加载数据
        self._product_loaded = False
        self._cs_loaded = False
        self._custom_kb_loaded = False
        # 标签缓存，避免重复重建下拉框
        self._last_cs_tags: tuple = ()

        self._init_ui()
        self._load_shops()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACING["page_margin"], SPACING["page_margin"], SPACING["page_margin"], SPACING["page_margin"])
        main_layout.setSpacing(12)

        # 顶部店铺选择栏
        shop_bar = QHBoxLayout()
        shop_bar.setSpacing(8)

        shop_label = QLabel("当前店铺:")
        shop_label.setFixedWidth(60)
        self.shop_combo = ComboBox()
        self.shop_combo.currentIndexChanged.connect(self._on_shop_changed)

        shop_bar.addWidget(shop_label)
        shop_bar.addWidget(self.shop_combo)
        shop_bar.addStretch()

        config_btn = PushButton("知识库配置")
        config_btn.clicked.connect(self._on_open_config)
        shop_bar.addWidget(config_btn)

        main_layout.addLayout(shop_bar)

        # SegmentedWidget 标签切换
        self.pivot = SegmentedWidget(self)
        self.pivot.setFixedWidth(400)
        self.stacked_widget = QStackedWidget(self)

        # 初始化四个标签页
        self._init_product_tab()
        self._init_cs_tab()
        self._init_custom_knowledge_tab()
        self._init_keywords_tab()

        # 添加页面到 stacked_widget
        self.stacked_widget.addWidget(self.product_tab)
        self.stacked_widget.addWidget(self.cs_tab)
        self.stacked_widget.addWidget(self.custom_kb_tab)
        self.stacked_widget.addWidget(self.keywords_tab)

        # 添加 SegmentedWidget 按钮（带懒加载）
        self.pivot.addItem(
            routeKey="product",
            text="产品知识",
            onClick=lambda: self._switch_to_product_tab()
        )
        self.pivot.addItem(
            routeKey="customer_service",
            text="客服知识",
            onClick=lambda: self._switch_to_cs_tab()
        )
        self.pivot.addItem(
            routeKey="custom",
            text="自定义知识库",
            onClick=lambda: self._switch_to_custom_kb_tab()
        )
        self.pivot.addItem(
            routeKey="keywords",
            text="关键词管理",
            onClick=lambda: self._switch_to_keywords_tab()
        )
        self.pivot.setCurrentItem("product")

        # 居中放置 SegmentedWidget
        pivot_layout = QHBoxLayout()
        pivot_layout.addStretch()
        pivot_layout.addWidget(self.pivot)
        pivot_layout.addStretch()
        main_layout.addLayout(pivot_layout)

        main_layout.addWidget(self.stacked_widget)

        self.setLayout(main_layout)
        logger.info("KnowledgeUI 初始化完成")

    def _load_shops(self):
        """加载店铺列表到下拉框"""
        self.shop_combo.clear()
        self._shop_cache.clear()
        shops = self.knowledge_service.get_all_shops()
        if not shops:
            self.shop_combo.addItem("请先在账号管理添加店铺")
            self.shop_combo.setItemData(0, None)
            return

        for i, shop in enumerate(shops):
            self.shop_combo.addItem(shop.shop_name)
            self.shop_combo.setItemData(i, shop.id)
            self._shop_cache[shop.id] = shop.shop_name

        # 默认选中第一个
        if len(shops) > 0:
            self.shop_combo.setCurrentIndex(0)
            self.current_shop_id = shops[0].id
            # 懒加载：只刷新当前可见的标签页
            if self.stacked_widget.currentWidget() == self.product_tab:
                self._refresh_product_table()
                self._product_loaded = True
            else:
                self._refresh_cs_table()
                self._cs_loaded = True

    def _switch_to_product_tab(self):
        """切换到产品知识标签页（懒加载）"""
        self.stacked_widget.setCurrentWidget(self.product_tab)
        if not self._product_loaded and self.current_shop_id is not None:
            self._refresh_product_table()
            self._product_loaded = True

    def _switch_to_cs_tab(self):
        """切换到客服知识标签页（懒加载）"""
        self.stacked_widget.setCurrentWidget(self.cs_tab)
        if not self._cs_loaded and self.current_shop_id is not None:
            self._refresh_cs_table()
            self._cs_loaded = True

    def _on_shop_changed(self, index: int):
        """店铺切换（懒加载，只刷新当前可见标签页）"""
        shop_id = self.shop_combo.itemData(index)
        if shop_id is not None:
            self.current_shop_id = shop_id
            self._product_loaded = False
            self._cs_loaded = False
            self._custom_kb_loaded = False
            self._last_cs_tags = ()
            # 只刷新当前可见的标签页
            if self.stacked_widget.currentWidget() == self.product_tab:
                self._refresh_product_table()
                self._product_loaded = True
            else:
                self._refresh_cs_table()
                self._cs_loaded = True

    def _init_product_tab(self):
        """初始化产品知识标签页"""
        self.product_tab = QWidget()
        layout = QVBoxLayout(self.product_tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.sync_btn = PrimaryPushButton("同步产品知识")
        self.sync_btn.clicked.connect(self._on_sync_clicked)
        self.add_product_btn = PushButton("添加产品知识")
        self.add_product_btn.clicked.connect(self._on_add_product_clicked)
        self.product_import_btn = PushButton("批量导入")
        self.product_import_btn.clicked.connect(self._on_product_batch_import_clicked)
        self.clear_btn = PushButton("清空全部")
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        toolbar.addWidget(self.sync_btn)
        toolbar.addWidget(self.add_product_btn)
        toolbar.addWidget(self.product_import_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.cancel_sync_btn = PushButton("取消")
        self.cancel_sync_btn.clicked.connect(self._on_cancel_sync)
        self.cancel_sync_btn.setVisible(False)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.cancel_sync_btn)
        layout.addLayout(progress_layout)

        # 产品表格
        self.product_table = TableWidget()
        self.product_table.setColumnCount(5)
        self.product_table.setHorizontalHeaderLabels(["商品ID", "商品名称", "价格", "同步时间", "操作"])
        self.product_table.setAlternatingRowColors(True)  # 交替行颜色
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 选择整行
        self.product_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 单选
        self.product_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.product_table.setColumnWidth(4, 180)  # 操作列固定宽度
        self.product_table.verticalHeader().setDefaultSectionSize(50)  # 设置默认行高
        layout.addWidget(self.product_table)

    def _init_cs_tab(self):
        """初始化客服知识标签页"""
        self.cs_tab = QWidget()
        layout = QVBoxLayout(self.cs_tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.add_cs_btn = PrimaryPushButton("添加客服知识")
        self.add_cs_btn.clicked.connect(self._on_add_cs_clicked)

        # 标签筛选
        self.tag_label = QLabel("标签筛选:")
        self.tag_combo = ComboBox()
        self.tag_combo.addItem("全部", None)
        self.tag_combo.currentIndexChanged.connect(self._on_tag_filter_changed)

        self.batch_import_btn = PushButton("批量导入")
        self.batch_import_btn.clicked.connect(self._on_batch_import_clicked)

        toolbar.addWidget(self.add_cs_btn)
        toolbar.addWidget(self.batch_import_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.tag_label)
        toolbar.addWidget(self.tag_combo)
        layout.addLayout(toolbar)

        # 客服知识表格
        self.cs_table = TableWidget()
        self.cs_table.setColumnCount(6)
        self.cs_table.setHorizontalHeaderLabels(["标题", "内容", "标签", "状态", "更新时间", "操作"])
        self.cs_table.setAlternatingRowColors(True)  # 交替行颜色
        self.cs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 选择整行
        self.cs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 单选
        self.cs_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.cs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.cs_table.setColumnWidth(0, 160)  # 标题列固定宽度
        self.cs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.cs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.cs_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.cs_table.setColumnWidth(5, 180)  # 操作列固定宽度
        self.cs_table.verticalHeader().setDefaultSectionSize(50)  # 设置默认行高
        layout.addWidget(self.cs_table)

    def _refresh_product_table(self):
        """刷新产品知识表格"""
        if self.current_shop_id is None:
            return

        products = self.knowledge_service.list_products_by_shop(self.current_shop_id)
        self.product_table.setRowCount(len(products))

        for row, product in enumerate(products):
            # 商品ID
            item = QTableWidgetItem(str(product.goods_id))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.product_table.setItem(row, 0, item)

            # 商品名称
            item = QTableWidgetItem(product.goods_name)
            self.product_table.setItem(row, 1, item)

            # 价格
            price_str = product.price or ""
            item = QTableWidgetItem(price_str)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.product_table.setItem(row, 2, item)

            # 同步时间
            dt_str = product.last_extracted_at.strftime("%Y-%m-%d %H:%M") if product.last_extracted_at else ""
            item = QTableWidgetItem(dt_str)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.product_table.setItem(row, 3, item)

            # 操作按钮 - 详情/编辑 删除
            # 使用容器放按钮
            cell_widget = QWidget()
            btn_layout = QHBoxLayout(cell_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(4)

            detail_btn = PushButton("详情")
            detail_btn.clicked.connect(lambda _, r=row: self._view_product(r))
            delete_btn = PushButton("删除")
            delete_btn.clicked.connect(lambda _, r=row: self._on_delete_product(r))

            btn_layout.addWidget(detail_btn)
            btn_layout.addWidget(delete_btn)
            cell_widget.setLayout(btn_layout)
            self.product_table.setCellWidget(row, 4, cell_widget)

    def _refresh_cs_table(self):
        """刷新客服知识表格"""
        if self.current_shop_id is None:
            return

        # 更新标签下拉框（只有标签变化时才重建，避免卡顿）
        all_tags = tuple(sorted(self.knowledge_service.get_all_tags(self.current_shop_id)))
        current_selection = self.tag_combo.currentData()
        if all_tags != self._last_cs_tags:
            self._last_cs_tags = all_tags

            self.tag_combo.blockSignals(True)
            self.tag_combo.clear()
            self.tag_combo.addItem("全部")
            self.tag_combo.setItemData(0, None)
            for i, tag in enumerate(all_tags, 1):
                self.tag_combo.addItem(tag)
                self.tag_combo.setItemData(i, tag)
            # 恢复选中
            if current_selection is None:
                self.tag_combo.setCurrentIndex(0)
            else:
                # 查找索引
                for i in range(self.tag_combo.count()):
                    if self.tag_combo.itemData(i) == current_selection:
                        self.tag_combo.setCurrentIndex(i)
                        break
            self.tag_combo.blockSignals(False)

        # 获取数据
        if current_selection is None:
            cs_list = self.knowledge_service.list_customer_service_with_disabled(self.current_shop_id)
        else:
            cs_list = self.knowledge_service.filter_customer_service_by_tag(self.current_shop_id, current_selection)

        self.cs_table.setRowCount(len(cs_list))

        for row, cs in enumerate(cs_list):
            # 标题
            item = QTableWidgetItem(cs.title)
            self.cs_table.setItem(row, 0, item)

            # 内容（截断避免过长）
            content_preview = cs.content
            if len(content_preview) > 60:
                content_preview = content_preview[:60] + "..."
            item = QTableWidgetItem(content_preview)
            item.setToolTip(cs.content)
            self.cs_table.setItem(row, 1, item)

            # 标签
            item = QTableWidgetItem(cs.tags or "")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cs_table.setItem(row, 2, item)

            # 状态
            status_text = "启用" if cs.enabled else "禁用"
            item = QTableWidgetItem(status_text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cs_table.setItem(row, 3, item)

            # 更新时间
            dt_str = cs.updated_at.strftime("%Y-%m-%d %H:%M") if cs.updated_at else ""
            item = QTableWidgetItem(dt_str)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cs_table.setItem(row, 4, item)

            # 操作按钮
            cell_widget = QWidget()
            btn_layout = QHBoxLayout(cell_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(4)

            edit_btn = PushButton("编辑")
            edit_btn.clicked.connect(lambda _, r=row: self._on_edit_cs(r))
            delete_btn = PushButton("删除")
            delete_btn.clicked.connect(lambda _, r=row: self._on_delete_cs(r))

            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(delete_btn)
            cell_widget.setLayout(btn_layout)
            self.cs_table.setCellWidget(row, 5, cell_widget)

            # 禁用行灰色显示
            if not cs.enabled:
                for col in range(self.cs_table.columnCount()):
                    if self.cs_table.item(row, col):
                        self.cs_table.item(row, col).setForeground(Qt.GlobalColor.gray)

    def _view_product(self, row: int):
        """查看/编辑产品详情"""
        product_id = self.product_table.item(row, 0).text()
        goods_id = int(product_id)
        product = self.knowledge_service.get_product_by_goods_id(self.current_shop_id, goods_id)
        if not product:
            QMessageBox.warning(self, "错误", "产品不存在")
            return

        dialog = ProductDetailDialog(product, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            content_changed = (
                product.extracted_content != data["extracted_content"]
                or product.goods_name != data["goods_name"]
            )
            img = data.get("image_path")
            with self.knowledge_service.get_session() as session:
                prod = session.get(ProductKnowledge, product.id)
                if prod:
                    prod.goods_name = data["goods_name"]
                    prod.price = data.get("price")
                    prod.extracted_content = data["extracted_content"]
                    if img:
                        prod.image_path = img
                    session.commit()
            # 内容变了才触发重索引
            if content_changed:
                self.knowledge_service._reindex_product(product)
            self._show_message("success", "更新成功")
            self._refresh_product_table()

    def _on_delete_product(self, row: int):
        """删除产品"""
        # 获取商品ID（第0列）
        product_id = self.product_table.item(row, 0).text()
        goods_id = int(product_id)
        product = self.knowledge_service.get_product_by_goods_id(self.current_shop_id, goods_id)
        if not product:
            QMessageBox.warning(self, "错误", "产品不存在")
            return

        confirm = QMessageBox.question(
            self, "确认删除",
            f"确定要删除产品 «{product.goods_name}» 吗？\n\n删除后无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success = self.knowledge_service.delete_product(product.id)
            if success:
                self._show_message("success", "删除成功")
                self._refresh_product_table()
            else:
                self._show_message("error", "删除失败")

    def _on_product_batch_import_clicked(self):
        """批量导入产品知识"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return

        from ui.file_import_dialog import FileImportDialog
        dialog = FileImportDialog(self, mode="product")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        entries = dialog.get_selected_product_entries()
        if not entries:
            return

        success = 0
        skipped = 0
        for entry in entries:
            goods_id_str = entry.get("goods_id", "").strip()
            goods_name = entry.get("goods_name", "").strip()
            price = entry.get("price", "").strip()
            content = entry.get("extracted_content", "").strip()

            if not goods_name:
                skipped += 1
                continue

            try:
                goods_id = int(goods_id_str) if goods_id_str else 0
            except ValueError:
                goods_id = 0

            try:
                self.knowledge_service.add_or_update_product(
                    shop_id=self.current_shop_id,
                    goods_id=goods_id,
                    goods_name=goods_name,
                    price=price,
                    extracted_content=content or None,
                )
                success += 1
            except Exception as e:
                logger.error(f"导入产品失败 [{goods_name}]: {e}")
                skipped += 1

        self._show_message("success", f"导入完成：成功 {success} 条，跳过 {skipped} 条")
        self._refresh_product_table()

    def _on_clear_clicked(self):
        """清空全部产品知识"""
        if self.current_shop_id is None:
            return

        confirm = QMessageBox.question(
            self, "确认清空",
            f"确定要清空当前店铺的所有产品知识吗？\n\n清空后无法恢复，请谨慎操作。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            total_deleted = self.knowledge_service.clear_products_by_shop(self.current_shop_id)
            self._show_message("success", f"已清空，共删除 {total_deleted} 条记录")
            self._refresh_product_table()

    def _on_sync_clicked(self):
        """点击同步按钮，弹出选择同步模式"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return

        # 获取当前选中的店铺
        shop_to_sync = self._get_shop_by_id(self.current_shop_id)
        if not shop_to_sync:
            self._show_message("error", "无法获取店铺信息")
            return

        # 弹出选择同步模式对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("选择同步模式")
        dialog.resize(350, 180)

        layout = QVBoxLayout(dialog)

        label = QLabel(f"即将同步店铺 «{shop_to_sync.shop_name}» 的产品知识，请选择同步模式:")
        layout.addWidget(label)

        incremental_btn = PushButton("增量同步（仅同步本地不存在的商品，推荐）")
        full_btn = PrimaryPushButton("全量同步（同步所有商品，覆盖已提取知识）")

        layout.addWidget(incremental_btn)
        layout.addWidget(full_btn)

        def start_sync(is_full):
            dialog.close()
            self._start_sync(shop_to_sync, is_full)

        incremental_btn.clicked.connect(lambda: start_sync(False))
        full_btn.clicked.connect(lambda: start_sync(True))

        dialog.setLayout(layout)
        dialog.exec()

    def _get_shop_by_id(self, shop_id: int) -> Optional[Shop]:
        """根据ID获取店铺对象"""
        # 根据ID查询店铺对象，同时预加载关联的accounts，避免懒加载问题
        with self.knowledge_service.get_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload
            stmt = select(Shop).where(Shop.id == shop_id).options(joinedload(Shop.accounts))
            return session.scalar(stmt)

    def _start_sync(self, shop: Shop, is_full_sync: bool):
        """开始同步"""
        # 获取pdd shop_id和user_id
        pdd_shop_id = shop.shop_id
        # 从shop.accounts[0]获取user_id，假设一个店铺只有一个账号
        if not shop.accounts:
            self._show_message("error", "店铺没有账号信息")
            return

        user_id = shop.accounts[0].user_id

        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.cancel_sync_btn.setVisible(True)
        self.sync_btn.setEnabled(False)

        # 创建工作线程
        self._sync_worker = SyncWorker(
            shop_db_id=shop.id,
            pdd_shop_id=pdd_shop_id,
            user_id=user_id,
            is_full_sync=is_full_sync,
            product_sync=self.product_sync,
            parent=self,
        )

        # 连接信号
        def on_progress(current: int, total: int, success: int, current_name: str, phase: str):
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            # 根据阶段显示不同的提示
            if phase == "fetching":
                self.progress_label.setText(f"[1/3] 抓取商品列表: {current_name} ({current}/{total})")
            elif phase == "saving_basic":
                self.progress_label.setText(f"[2/3] 保存商品信息: {current_name} ({current}/{total}, 成功 {success})")
                # 第二阶段开始后刷新一次表格，让用户能看到商品
                if current == 1 or current % 10 == 0:
                    self._refresh_product_table()
            elif phase == "extracting":
                self.progress_label.setText(f"[3/3] 提取商品知识: {current_name} ({current}/{total}, 成功 {success})")
                # 提取阶段也定期刷新，显示更新的知识
                if current % 5 == 0:
                    self._refresh_product_table()
            else:
                self.progress_label.setText(f"正在同步: {current_name} ({current}/{total}, 成功 {success})")

        def on_finished(success: int, failed: int, cancelled: bool):
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            self.cancel_sync_btn.setVisible(False)
            self.sync_btn.setEnabled(True)

            # 最后刷新一次表格
            self._refresh_product_table()

            if cancelled:
                self._show_message("info", "同步已取消")
            else:
                msg = f"同步完成: 成功 {success}, 失败 {failed}"
                self._show_message("success", msg)

        self._sync_worker.progress_updated.connect(on_progress)
        self._sync_worker.sync_finished.connect(on_finished)
        self._sync_worker.start()

    def _on_cancel_sync(self):
        """取消同步"""
        if hasattr(self, '_sync_worker') and self._sync_worker.isRunning():
            self.product_sync.cancel()
            self.cancel_sync_btn.setEnabled(False)

    def _on_add_cs_clicked(self):
        """添加客服知识"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return

        dialog = CsAddEditDialog(self.current_shop_id, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.knowledge_service.add_customer_service(
                shop_id=self.current_shop_id,
                title=data["title"],
                content=data["content"],
                tags=data["tags"],
                enabled=data["enabled"],
            )
            self._show_message("success", "添加成功")
            self._refresh_cs_table()

    def _on_batch_import_clicked(self):
        """批量导入客服知识（支持 TXT / Excel）"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return

        from ui.file_import_dialog import FileImportDialog
        dialog = FileImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        entries = dialog.get_selected_entries()
        tags = dialog.get_tags()

        if not entries:
            return

        rows = []
        for entry in entries:
            rows.append({
                "title": entry["title"],
                "content": entry["content"],
                "tags": tags,
            })

        success, skipped = self.knowledge_service.batch_import_customer_service(
            self.current_shop_id, rows
        )
        self._show_message("success", f"导入完成：成功 {success} 条，跳过 {skipped} 条")
        self._refresh_cs_table()

    def _on_edit_cs(self, row: int):
        """编辑客服知识"""
        cs_id = self._get_cs_id_from_row(row)
        cs = self.knowledge_service.get_customer_service_by_id(cs_id)
        if not cs:
            self._show_message("error", "知识不存在")
            return

        dialog = CsAddEditDialog(cs.shop_id, cs, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            updated = self.knowledge_service.update_customer_service(
                cs_id,
                title=data["title"],
                content=data["content"],
                tags=data["tags"],
                enabled=data["enabled"],
            )
            if updated:
                self._show_message("success", "更新成功")
                self._refresh_cs_table()

    def _on_delete_cs(self, row: int):
        """删除客服知识"""
        cs_id = self._get_cs_id_from_row(row)
        cs = self.knowledge_service.get_customer_service_by_id(cs_id)
        if not cs:
            self._show_message("error", "知识不存在")
            return

        confirm = QMessageBox.question(
            self, "确认删除",
            f"确定要删除客服知识 «{cs.title}» 吗？\n\n删除后无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success = self.knowledge_service.delete_customer_service(cs_id)
            if success:
                self._show_message("success", "删除成功")
                self._refresh_cs_table()
            else:
                self._show_message("error", "删除失败")

    def _get_cs_id_from_row(self, row: int) -> int:
        """从表格行获取客服知识ID，这里需要查询，因为表格没有保存id"""
        # 标题在第0列
        title = self.cs_table.item(row, 0).text()
        # 直接查询当前店铺下的客服知识
        with self.knowledge_service.get_session() as session:
            from sqlalchemy import select
            stmt = select(CustomerServiceKnowledge).where(
                CustomerServiceKnowledge.shop_id == self.current_shop_id,
                CustomerServiceKnowledge.title == title,
            )
            cs = session.scalar(stmt)
            if cs:
                return cs.id
        return 0

    def _on_tag_filter_changed(self, index: int):
        """标签筛选变化"""
        self._refresh_cs_table()

    def _show_message(self, level: str, content: str):
        """显示消息条"""
        method = getattr(InfoBar, level)
        method(
            title="",
            content=content,
            orient=Qt.Orientation.Vertical,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    # ===== 关键词管理 =====

    def _init_keywords_tab(self):
        """初始化关键词管理标签页"""
        self.keywords_tab = QWidget()
        self.keywords_tab.setObjectName("keywordsTab")
        layout = QVBoxLayout(self.keywords_tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.kw_stats_label = QLabel("共 0 个关键词")
        toolbar.addWidget(self.kw_stats_label)
        toolbar.addStretch()

        import_btn = PushButton("批量导入")
        import_btn.setIcon(FIF.FOLDER_ADD)
        import_btn.clicked.connect(self._on_keyword_import)
        toolbar.addWidget(import_btn)

        add_btn = PrimaryPushButton("添加关键词")
        add_btn.setIcon(FIF.ADD)
        add_btn.clicked.connect(self._on_keyword_add)
        toolbar.addWidget(add_btn)

        layout.addLayout(toolbar)

        # 关键词表格
        from ui.keyword_ui import KeywordTableWidget
        self.kw_table = KeywordTableWidget()
        self.kw_table.edit_clicked.connect(self._on_keyword_edit)
        self.kw_table.delete_clicked.connect(self._on_keyword_delete)
        layout.addWidget(self.kw_table, 1)

        self._keywords_loaded = False

    def _switch_to_keywords_tab(self):
        """切换到关键词管理标签页（懒加载）"""
        self.stacked_widget.setCurrentWidget(self.keywords_tab)
        if not self._keywords_loaded:
            self._keywords_loaded = True
            self._load_keywords()

    def _load_keywords(self):
        """加载关键词数据"""
        try:
            from database.db_manager import db_manager
            keywords = db_manager.get_all_keywords()
            self._kw_data = [{"keyword": kw["keyword"]} for kw in keywords]
            if not self._kw_data:
                self._init_sample_keywords()
            self._refresh_keyword_table()
        except Exception:
            self._kw_data = []
            self._init_sample_keywords()

    def _init_sample_keywords(self):
        """初始化示例关键词到数据库"""
        from database.db_manager import db_manager
        sample_keywords = [
            "转人工", "人工客服", "真人", "客服", "人工", "工单", "好评",
            "取消订单", "改地址", "转售后客服", "转售后", "返现", "过敏",
            "退款", "没有效果", "骗人", "投诉", "纠纷", "开发票", "开票",
            "烂", "取消", "备注",
        ]
        for keyword in sample_keywords:
            if db_manager.add_keyword(keyword):
                self._kw_data.append({"keyword": keyword})

    def _refresh_keyword_table(self):
        """刷新关键词表格"""
        self.kw_table.clearTable()
        for kw in self._kw_data:
            self.kw_table.addKeyword(kw["keyword"])
        self.kw_stats_label.setText(f"共 {len(self._kw_data)} 个关键词")

    def _on_keyword_add(self):
        """添加关键词"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "添加关键词", "请输入关键词:")
        if ok and text.strip():
            from database.db_manager import db_manager
            if db_manager.add_keyword(text.strip()):
                self._kw_data.append({"keyword": text.strip()})
                self._refresh_keyword_table()
                self._show_message("success", f"关键词 \"{text.strip()}\" 添加成功")
            else:
                self._show_message("warning", f"关键词 \"{text.strip()}\" 已存在")

    def _on_keyword_import(self):
        """批量导入关键词"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self, "批量导入关键词",
            "请输入关键词，每行一个:\n(空行将被忽略)"
        )
        if ok and text.strip():
            keywords = [line.strip() for line in text.split("\n") if line.strip()]
            success_count = 0
            from database.db_manager import db_manager
            for keyword in keywords:
                if db_manager.add_keyword(keyword):
                    self._kw_data.append({"keyword": keyword})
                    success_count += 1
            self._refresh_keyword_table()
            self._show_message("success", f"导入完成: 成功 {success_count} / {len(keywords)} 个")

    def _on_keyword_edit(self, keyword: str):
        """编辑关键词"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "编辑关键词", "请修改关键词:", text=keyword)
        if ok and text.strip() and text.strip() != keyword:
            from database.db_manager import db_manager
            if db_manager.update_keyword(keyword, text.strip()):
                for i, kw in enumerate(self._kw_data):
                    if kw["keyword"] == keyword:
                        self._kw_data[i]["keyword"] = text.strip()
                        break
                self._refresh_keyword_table()
                self._show_message("success", f"关键词已修改: \"{keyword}\" → \"{text.strip()}\"")

    def _on_keyword_delete(self, keyword: str):
        """删除关键词"""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除关键词 \"{keyword}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            from database.db_manager import db_manager
            if db_manager.delete_keyword(keyword):
                self._kw_data = [k for k in self._kw_data if k["keyword"] != keyword]
                self._refresh_keyword_table()

    # ===== 自定义知识库 =====

    def _init_custom_knowledge_tab(self):
        """初始化自定义知识库标签页"""
        self.custom_kb_tab = QWidget()
        layout = QVBoxLayout(self.custom_kb_tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # --- 输入表单 ---
        form_group = QFrame()
        form_group.setStyleSheet(f"QFrame {{ background: {COLORS['page_bg_alt']}; border-radius: 8px; padding: 8px; }}")
        form_layout = QVBoxLayout(form_group)
        form_layout.setSpacing(6)

        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("标题:"))
        self.custom_title_input = QLineEdit()
        self.custom_title_input.setPlaceholderText("输入知识标题，如：退换货政策")
        title_layout.addWidget(self.custom_title_input)
        form_layout.addLayout(title_layout)

        content_label = QLabel("内容:")
        form_layout.addWidget(content_label)
        self.custom_content_input = QTextEdit()
        self.custom_content_input.setPlaceholderText("输入自定义知识内容，支持长文本自动分块...")
        self.custom_content_input.setMinimumHeight(120)
        form_layout.addWidget(self.custom_content_input)

        chunk_row = QHBoxLayout()
        chunk_row.addWidget(QLabel("分块大小:"))
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(100, 2000)
        self.chunk_size_spin.setValue(500)
        chunk_row.addWidget(self.chunk_size_spin)
        chunk_row.addSpacing(12)
        chunk_row.addWidget(QLabel("分块重叠:"))
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 500)
        self.chunk_overlap_spin.setValue(50)
        chunk_row.addWidget(self.chunk_overlap_spin)
        chunk_row.addStretch()
        form_layout.addLayout(chunk_row)

        btn_row = QHBoxLayout()
        preview_btn = PushButton("预览分块")
        preview_btn.clicked.connect(self._on_preview_chunks)
        save_btn = PrimaryPushButton("保存并索引")
        save_btn.clicked.connect(self._on_save_custom_kb)
        file_import_btn = PushButton("文件导入")
        file_import_btn.clicked.connect(self._on_custom_kb_file_import)
        btn_row.addWidget(preview_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(file_import_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        # 分块预览
        self.chunk_preview_label = QLabel("")
        self.chunk_preview_label.setWordWrap(True)
        self.chunk_preview_label.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 12px; padding: 4px;")
        self.chunk_preview_label.setVisible(False)
        form_layout.addWidget(self.chunk_preview_label)

        layout.addWidget(form_group)

        # --- 已索引条目表格 ---
        self.custom_kb_table = TableWidget()
        self.custom_kb_table.setColumnCount(5)
        self.custom_kb_table.setHorizontalHeaderLabels(["ID", "标题", "内容预览", "分块数", "操作"])
        self.custom_kb_table.setAlternatingRowColors(True)
        self.custom_kb_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.custom_kb_table.verticalHeader().setVisible(False)
        self.custom_kb_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.custom_kb_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_kb_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_kb_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.custom_kb_table.setColumnWidth(4, 180)
        self.custom_kb_table.verticalHeader().setDefaultSectionSize(50)
        layout.addWidget(self.custom_kb_table)

    def _switch_to_custom_kb_tab(self):
        """切换到自定义知识库标签页（懒加载）"""
        self.stacked_widget.setCurrentWidget(self.custom_kb_tab)
        if not self._custom_kb_loaded and self.current_shop_id is not None:
            self._refresh_custom_kb_table()
            self._custom_kb_loaded = True

    def _on_preview_chunks(self):
        """预览分块结果"""
        if not self.chunking_service:
            self._show_message("warning", "分块服务未初始化")
            return
        content = self.custom_content_input.toPlainText().strip()
        if not content:
            self._show_message("warning", "请输入内容")
            return
        chunk_size = self.chunk_size_spin.value()
        chunk_overlap = self.chunk_overlap_spin.value()
        self.chunking_service.chunk_size = chunk_size
        self.chunking_service.chunk_overlap = chunk_overlap
        preview = self.chunking_service.preview_chunks(content)
        lines = [f"共 {len(preview)} 个分块:"]
        for p in preview:
            lines.append(f"  #{p['index']} [{p['length']}字]: {p['text'][:80]}...")
        text = "\n".join(lines)
        self.chunk_preview_label.setText(text)
        self.chunk_preview_label.setVisible(True)

    def _on_save_custom_kb(self):
        """保存自定义知识条目并索引"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return
        title = self.custom_title_input.text().strip()
        content = self.custom_content_input.toPlainText().strip()
        if not title or not content:
            self._show_message("warning", "标题和内容不能为空")
            return
        if not self.custom_kb_service:
            self._show_message("error", "自定义知识服务未初始化")
            return

        self.custom_title_input.setEnabled(False)
        self.custom_content_input.setEnabled(False)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.custom_kb_service.save_and_index(
                    self.current_shop_id, title, content
                )
            )
            loop.close()
            chunk_count = result.get("chunk_count", 0)
            self._show_message("success", f"保存成功，共 {chunk_count} 个分块")
            self._refresh_custom_kb_table()
            self.custom_title_input.clear()
            self.custom_content_input.clear()
            self.chunk_preview_label.setVisible(False)
        except Exception as e:
            logger.error(f"保存自定义知识失败: {e}")
            self._show_message("error", f"保存失败: {e}")
        finally:
            self.custom_title_input.setEnabled(True)
            self.custom_content_input.setEnabled(True)

    def _on_custom_kb_file_import(self):
        """自定义知识库文件导入"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return

        from ui.file_import_dialog import FileImportDialog
        dialog = FileImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        entries = dialog.get_selected_entries()
        if not entries:
            return

        if not self.custom_kb_service:
            self._show_message("error", "自定义知识库服务未初始化")
            return

        import asyncio
        success = 0
        for entry in entries:
            try:
                if not entry["title"].strip():
                    entry["title"] = entry["content"][:60]
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    self.custom_kb_service.save_and_index(
                        shop_id=self.current_shop_id,
                        title=entry["title"],
                        content=entry["content"],
                    )
                )
                loop.close()
                success += 1
            except Exception as e:
                logger.error(f"导入自定义知识失败 [{entry['title']}]: {e}")

        self._show_message("success", f"导入完成：成功 {success} / {len(entries)} 条")
        self._refresh_custom_kb_table()

    def _refresh_custom_kb_table(self):
        """刷新自定义知识表格"""
        if self.current_shop_id is None or not self.custom_kb_service:
            return
        entries = self.custom_kb_service.list_entries(self.current_shop_id)
        self.custom_kb_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            item = QTableWidgetItem(str(entry.id))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.custom_kb_table.setItem(row, 0, item)

            self.custom_kb_table.setItem(row, 1, QTableWidgetItem(entry.title))

            preview = entry.content[:60] + "..." if len(entry.content) > 60 else entry.content
            self.custom_kb_table.setItem(row, 2, QTableWidgetItem(preview))

            item = QTableWidgetItem(str(entry.chunk_count))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.custom_kb_table.setItem(row, 3, item)

            cell = QWidget()
            btn_layout = QHBoxLayout(cell)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(4)
            reindex_btn = PushButton("重新索引")
            reindex_btn.clicked.connect(lambda _, e=entry: self._on_reindex_custom_kb(e))
            delete_btn = PushButton("删除")
            delete_btn.clicked.connect(lambda _, e=entry: self._on_delete_custom_kb(e))
            btn_layout.addWidget(reindex_btn)
            btn_layout.addWidget(delete_btn)
            cell.setLayout(btn_layout)
            self.custom_kb_table.setCellWidget(row, 4, cell)

    def _on_reindex_custom_kb(self, entry: CustomKnowledge):
        """重新索引自定义知识"""
        if not self.vector_sync:
            self._show_message("error", "向量索引服务未初始化")
            return
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            # 用纯值索引，避免 ORM detached 问题
            loop.run_until_complete(
                self.vector_sync.index_raw(
                    "custom", entry.id, entry.shop_id,
                    f"{entry.title}\n{entry.content}",
                )
            )
            self._show_message("success", "重新索引完成")
            self._refresh_custom_kb_table()
        except Exception as e:
            logger.error(f"重新索引失败: {e}")
            self._show_message("error", f"重新索引失败: {e}")
        finally:
            loop.close()

    def _on_delete_custom_kb(self, entry: CustomKnowledge):
        """删除自定义知识"""
        if not self.custom_kb_service:
            return
        confirm = QMessageBox.question(
            self, "确认删除",
            f"确定要删除自定义知识 «{entry.title}» 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.custom_kb_service.delete_entry(entry.id)
            if self.vector_sync:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self.vector_sync.remove_custom_entry(entry.id, entry.shop_id)
                )
                loop.close()
            self._show_message("success", "删除成功")
            self._refresh_custom_kb_table()
        except Exception as e:
            logger.error(f"删除自定义知识失败: {e}")
            self._show_message("error", f"删除失败: {e}")

    def _on_migrate_clicked(self):
        """触发向量索引迁移"""
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return
        if not self.vector_sync:
            self._show_message("error", "向量索引服务未初始化")
            return

        reply = QMessageBox.question(
            self, "确认迁移",
            "将当前店铺的产品知识和客服知识迁移到向量索引。\n"
            "此操作会调用 Embedding API（可能产生费用）。\n\n"
            "确认继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        # self.migrate_btn.setEnabled(False)
        # self.sync_btn.setEnabled(False)

        import asyncio
        import threading

        def run_migration():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            def progress_cb(progress):
                self.progress_label.setText(
                    f"[{progress.source_type}] {progress.current_name} ({progress.current}/{progress.total})"
                )
                self.progress_bar.setMaximum(progress.total)
                self.progress_bar.setValue(progress.current)

            try:
                result = loop.run_until_complete(
                    self.vector_sync.migrate_all(
                        self.current_shop_id,
                        progress_callback=progress_cb,
                    )
                )
                loop.close()
                self.progress_bar.setVisible(False)
                self.progress_label.setVisible(False)
                # self.migrate_btn.setEnabled(True)
                # self.sync_btn.setEnabled(True)
                self._show_message("success",
                    f"迁移完成: 成功 {result['succeeded']}, 失败 {result['failed']}")
            except Exception as e:
                loop.close()
                logger.error(f"迁移失败: {e}")
                self._show_message("error", f"迁移失败: {e}")

        threading.Thread(target=run_migration, daemon=True).start()

    # ===== 知识库全局配置弹窗 =====

    def _on_open_config(self):
        dialog = KnowledgeConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._show_message("success", "知识库配置已保存，重启后全部生效")

    # ===== 手动添加产品知识 =====

    def _on_add_product_clicked(self):
        if self.current_shop_id is None:
            self._show_message("warning", "请先选择店铺")
            return
        dialog = ProductAddDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                product = self.knowledge_service.add_or_update_product(
                    shop_id=self.current_shop_id,
                    goods_id=data["goods_id"],
                    goods_name=data["goods_name"],
                    price=data.get("price"),
                    extracted_content=data.get("content"),
                    image_path=data.get("image_path"),
                )
                self._show_message("success", f"添加成功，自动同步向量索引")
                self._refresh_product_table()
            except Exception as e:
                self._show_message("error", f"添加失败: {e}")

    def showEvent(self, event):
        """显示时刷新"""
        super().showEvent(event)
        # 刷新店铺列表，可能有新增
        self._load_shops()
