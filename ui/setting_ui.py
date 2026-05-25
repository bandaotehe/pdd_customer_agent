# 设置界面

import json
import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QWidget, QLabel,
                            QFormLayout, QGroupBox, QMessageBox)
from PyQt6.QtGui import QFont
from qfluentwidgets import (CardWidget, SubtitleLabel, CaptionLabel, BodyLabel,
                           PrimaryPushButton, PushButton, StrongBodyLabel,
                           LineEdit, ComboBox, ScrollArea, FluentIcon as FIF,
                           InfoBar, InfoBarPosition, TextEdit, PasswordLineEdit,
                           TimePicker, CheckBox, SpinBox)
from PyQt6.QtCore import QTime
from utils.logger_loguru import get_logger
from config import config, config_base
from ui.theme import COLORS, SPACING, scrollbar_style, font as theme_font




class LLMConfigCard(CardWidget):
    """LLM配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 卡片标题
        title_label = StrongBodyLabel("LLM模型配置")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        # API Base URL
        self.api_base_edit = LineEdit()
        self.api_base_edit.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
        self.api_base_edit.setText("https://ark.cn-beijing.volces.com/api/v3")
        form_layout.addRow("API Base URL:", self.api_base_edit)

        # API Key
        self.api_key_edit = PasswordLineEdit()
        self.api_key_edit.setPlaceholderText("输入您的 API Key")
        form_layout.addRow("API Key:", self.api_key_edit)

        # Model Name
        self.model_name_edit = LineEdit()
        self.model_name_edit.setPlaceholderText("输入模型名称，如：doubao-seed-1-6-flash-250828")
        form_layout.addRow("模型名称:", self.model_name_edit)

        # 视觉支持
        self.supports_vision_check = CheckBox("支持图片/视频输入（视觉模型）")
        form_layout.addRow("视觉能力:", self.supports_vision_check)

        layout.addLayout(form_layout)

        # 说明文本
        description_label = CaptionLabel(
            "配置LLM模型的连接参数。\n"
            "支持OpenAI兼容的API接口。启用视觉能力后，模型可直接理解客户发来的图片。"
        )
        description_label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(description_label)

    def getConfig(self) -> dict:
        """获取配置"""
        return {
            "api_base": self.api_base_edit.text().strip() or "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": self.api_key_edit.text().strip(),
            "model_name": self.model_name_edit.text().strip(),
            "supports_vision": self.supports_vision_check.isChecked(),
        }

    def setConfig(self, config: dict):
        """设置配置"""
        self.api_base_edit.setText(config.get("api_base", "https://ark.cn-beijing.volces.com/api/v3"))
        self.api_key_edit.setText(config.get("api_key", ""))
        self.model_name_edit.setText(config.get("model_name", ""))
        self.supports_vision_check.setChecked(config.get("supports_vision", False))


class PromptConfigCard(CardWidget):
    """提示词配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 卡片标题
        title_label = StrongBodyLabel("AI提示词配置")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        # 行为指令（用户唯一可配置的字段）
        self.instructions_edit = TextEdit()
        self.instructions_edit.setPlaceholderText("输入行为指令，每行一条")
        self.instructions_edit.setMaximumHeight(200)
        form_layout.addRow("行为指令:", self.instructions_edit)

        layout.addLayout(form_layout)

        # 说明文本
        description_label = CaptionLabel(
            "配置AI助手的行为指令。\n"
            "角色描述和工具说明由系统自动管理，无需手动配置。"
        )
        description_label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(description_label)

    def getConfig(self) -> dict:
        """获取配置"""
        return {
            "instructions": [
                line.strip() for line in self.instructions_edit.toPlainText().splitlines() if line.strip()
            ]
        }

    def setConfig(self, config: dict):
        """设置配置"""
        instructions = config.get("instructions", [])
        if isinstance(instructions, list):
            self.instructions_edit.setPlainText("\n".join(instructions))
        elif isinstance(instructions, str):
            self.instructions_edit.setPlainText(instructions)


class BusinessHoursCard(CardWidget):
    """业务时间配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 卡片标题
        title_label = StrongBodyLabel("业务时间设置")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        # 开始时间
        self.start_time_picker = TimePicker()
        self.start_time_picker.setTime(QTime(8, 0))  # 默认8:00
        form_layout.addRow("开始时间:", self.start_time_picker)

        # 结束时间
        self.end_time_picker = TimePicker()
        self.end_time_picker.setTime(QTime(23, 0))  # 默认23:00
        form_layout.addRow("结束时间:", self.end_time_picker)

        layout.addLayout(form_layout)

        # 说明文本
        description_label = CaptionLabel(
            "设置AI客服的工作时间。在工作时间内，系统将自动响应客户消息。\n"
            "在非工作时间，系统将不会自动回复。"
        )
        description_label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(description_label)

    def getConfig(self) -> dict:
        """获取配置"""
        return {
            "businessHours": {
                "start": self.start_time_picker.getTime().toString("HH:mm"),
                "end": self.end_time_picker.getTime().toString("HH:mm")
            },
            "business_hours": {
                "start": self.start_time_picker.getTime().toString("HH:mm"),
                "end": self.end_time_picker.getTime().toString("HH:mm")
            }
        }

    def setConfig(self, config: dict):
        """设置配置"""
        # 支持新旧配置格式
        business_hours = config.get("businessHours", config.get("business_hours", {}))

        # 解析开始时间
        start_time_str = business_hours.get("start", "08:00")
        start_time = QTime.fromString(start_time_str, "HH:mm")
        if start_time.isValid():
            self.start_time_picker.setTime(start_time)

        # 解析结束时间
        end_time_str = business_hours.get("end", "23:00")
        end_time = QTime.fromString(end_time_str, "HH:mm")
        if end_time.isValid():
            self.end_time_picker.setTime(end_time)


class OSSConfigCard(CardWidget):
    """OSS 对象存储配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title_label = StrongBodyLabel("OSS 对象存储")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.oss_key_id = LineEdit()
        self.oss_key_id.setPlaceholderText("AccessKey ID")
        form_layout.addRow("AccessKey ID:", self.oss_key_id)

        self.oss_key_secret = PasswordLineEdit()
        self.oss_key_secret.setPlaceholderText("AccessKey Secret")
        form_layout.addRow("AccessKey Secret:", self.oss_key_secret)

        self.oss_endpoint = LineEdit()
        self.oss_endpoint.setPlaceholderText("oss-cn-shenzhen.aliyuncs.com")
        form_layout.addRow("Endpoint:", self.oss_endpoint)

        self.oss_bucket = LineEdit()
        self.oss_bucket.setPlaceholderText("Bucket 名称")
        form_layout.addRow("Bucket:", self.oss_bucket)

        layout.addLayout(form_layout)

        desc = CaptionLabel("阿里云 OSS 对象存储配置，用于产品图片上传和托管。")
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(desc)

    def getConfig(self) -> dict:
        return {
            "access_key_id": self.oss_key_id.text().strip(),
            "access_key_secret": self.oss_key_secret.text().strip(),
            "endpoint": self.oss_endpoint.text().strip(),
            "bucket": self.oss_bucket.text().strip(),
        }

    def setConfig(self, cfg: dict):
        self.oss_key_id.setText(cfg.get("access_key_id", ""))
        self.oss_key_secret.setText(cfg.get("access_key_secret", ""))
        self.oss_endpoint.setText(cfg.get("endpoint", "oss-cn-shenzhen.aliyuncs.com"))
        self.oss_bucket.setText(cfg.get("bucket", ""))


class KnowledgeBaseConfigCard(CardWidget):
    """知识库配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title_label = StrongBodyLabel("知识库配置")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        # ── Embedding ──
        emb_group = QGroupBox("嵌入模型 (Embedding)")
        emb_layout = QFormLayout(emb_group)
        emb_layout.setSpacing(8)

        self.emb_provider = ComboBox()
        self.emb_provider.addItems(["openai", "local"])
        emb_layout.addRow("提供方:", self.emb_provider)

        self.emb_model = LineEdit()
        self.emb_model.setPlaceholderText("qwen3-embedding-8b")
        emb_layout.addRow("模型名称:", self.emb_model)

        self.emb_api_key = PasswordLineEdit()
        self.emb_api_key.setPlaceholderText("为空则复用 LLM API Key")
        emb_layout.addRow("API Key:", self.emb_api_key)

        self.emb_api_base = LineEdit()
        self.emb_api_base.setPlaceholderText("为空则复用 LLM API Base")
        emb_layout.addRow("API Base:", self.emb_api_base)

        self.emb_dim = SpinBox()
        self.emb_dim.setRange(128, 8192)
        self.emb_dim.setValue(1536)
        emb_layout.addRow("向量维度:", self.emb_dim)

        layout.addWidget(emb_group)

        # ── Reranker ──
        rerank_group = QGroupBox("重排序 (Reranker)")
        rerank_layout = QFormLayout(rerank_group)
        rerank_layout.setSpacing(8)

        self.rerank_provider = ComboBox()
        self.rerank_provider.addItems(["api", "local"])
        rerank_layout.addRow("提供方:", self.rerank_provider)

        self.rerank_model = LineEdit()
        self.rerank_model.setPlaceholderText("qwen3-reranker-8b")
        rerank_layout.addRow("模型名称:", self.rerank_model)

        self.rerank_api_key = PasswordLineEdit()
        self.rerank_api_key.setPlaceholderText("为空则复用 LLM API Key")
        rerank_layout.addRow("API Key:", self.rerank_api_key)

        self.rerank_api_base = LineEdit()
        self.rerank_api_base.setPlaceholderText("为空则复用 LLM API Base")
        rerank_layout.addRow("API Base:", self.rerank_api_base)

        layout.addWidget(rerank_group)

        # ── 分块参数 ──
        chunk_group = QGroupBox("分块参数")
        chunk_layout = QFormLayout(chunk_group)
        chunk_layout.setSpacing(8)

        self.chunk_size = SpinBox()
        self.chunk_size.setRange(100, 2000)
        self.chunk_size.setValue(500)
        chunk_layout.addRow("分块大小（字符）:", self.chunk_size)

        self.chunk_overlap = SpinBox()
        self.chunk_overlap.setRange(0, 500)
        self.chunk_overlap.setValue(50)
        chunk_layout.addRow("分块重叠（字符）:", self.chunk_overlap)

        layout.addWidget(chunk_group)

        desc = CaptionLabel("知识库 Embedding、Reranker 和文档分块参数。修改后需重新同步向量索引。")
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(desc)

    def getConfig(self) -> dict:
        return {
            "embedding": {
                "provider": self.emb_provider.currentText(),
                "model_name": self.emb_model.text().strip(),
                "api_key": self.emb_api_key.text().strip(),
                "api_base": self.emb_api_base.text().strip(),
                "dimension": self.emb_dim.value(),
            },
            "reranker": {
                "provider": self.rerank_provider.currentText(),
                "model_name": self.rerank_model.text().strip(),
                "api_key": self.rerank_api_key.text().strip(),
                "api_base": self.rerank_api_base.text().strip(),
            },
            "chunk_size": self.chunk_size.value(),
            "chunk_overlap": self.chunk_overlap.value(),
        }

    def setConfig(self, cfg: dict):
        emb = cfg.get("embedding", {})
        self.emb_provider.setCurrentText(emb.get("provider", "openai"))
        self.emb_model.setText(emb.get("model_name", ""))
        self.emb_api_key.setText(emb.get("api_key", ""))
        self.emb_api_base.setText(emb.get("api_base", ""))
        self.emb_dim.setValue(emb.get("dimension", 1536))

        rerank = cfg.get("reranker", {})
        self.rerank_provider.setCurrentText(rerank.get("provider", "local"))
        self.rerank_model.setText(rerank.get("model_name", ""))
        self.rerank_api_key.setText(rerank.get("api_key", ""))
        self.rerank_api_base.setText(rerank.get("api_base", ""))

        self.chunk_size.setValue(cfg.get("chunk_size", 500))
        self.chunk_overlap.setValue(cfg.get("chunk_overlap", 50))


class DatabaseConfigCard(CardWidget):
    """数据库路径配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title_label = StrongBodyLabel("数据库")
        title_label.setFont(theme_font("body", QFont.Weight.Bold))
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.db_path_edit = LineEdit()
        self.db_path_edit.setPlaceholderText("./temp/channel_shop.db")
        form_layout.addRow("数据库路径:", self.db_path_edit)

        layout.addLayout(form_layout)

        desc = CaptionLabel("SQLite 数据库文件路径，修改后需重启应用生效。")
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 8px 0;")
        layout.addWidget(desc)

    def getConfig(self) -> dict:
        return {"db_path": self.db_path_edit.text().strip()}

    def setConfig(self, cfg: dict):
        self.db_path_edit.setText(cfg.get("db_path", "./temp/channel_shop.db"))


class SettingUI(QFrame):
    """设置界面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.logger = get_logger("SettingUI")
        self.setupUI()
        self.loadConfig()

        # 设置对象名
        self.setObjectName("设置")

    def setupUI(self):
        """设置主界面UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACING["page_margin"], SPACING["page_margin"], SPACING["page_margin"], SPACING["page_margin"])
        main_layout.setSpacing(25)

        # 创建头部区域
        header_widget = self.createHeaderWidget()

        # 创建内容区域
        content_widget = self.createContentWidget()

        # 连接按钮信号
        self.save_btn.clicked.connect(self.onSaveConfig)
        self.reset_btn.clicked.connect(self.onResetConfig)

        # 添加到主布局
        main_layout.addWidget(header_widget)
        main_layout.addWidget(content_widget, 1)

    def createHeaderWidget(self):
        """创建头部区域"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(20)

        # 标题
        title_label = SubtitleLabel("系统设置")
        title_label.setFont(theme_font("large", QFont.Weight.Bold))

        # 描述
        description_label = CaptionLabel("配置AI客服的基本参数和工作时间")
        description_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        # 左侧标题区域
        title_area = QWidget()
        title_layout = QVBoxLayout(title_area)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(5)
        title_layout.addWidget(title_label)
        title_layout.addWidget(description_label)

        # 按钮区域
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)

        # 重置按钮
        self.reset_btn = PushButton("重置")
        self.reset_btn.setIcon(FIF.UPDATE)
        self.reset_btn.setFixedSize(80, 40)

        # 保存按钮
        self.save_btn = PrimaryPushButton("保存")
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.setFixedSize(100, 40)

        buttons_layout.addWidget(self.reset_btn)
        buttons_layout.addWidget(self.save_btn)

        # 添加到头部布局
        header_layout.addWidget(title_area)
        header_layout.addStretch()
        header_layout.addWidget(buttons_widget)

        return header_widget

    def createContentWidget(self):
        """创建内容区域"""
        # 滚动区域
        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 去除边框（使用主题样式）
        scroll_area.setStyleSheet(scrollbar_style())

        # 内容容器
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 创建配置卡片
        self.llm_config_card = LLMConfigCard()
        self.prompt_config_card = PromptConfigCard()
        self.business_hours_card = BusinessHoursCard()
        self.oss_config_card = OSSConfigCard()
        self.kb_config_card = KnowledgeBaseConfigCard()
        self.db_config_card = DatabaseConfigCard()

        # 添加到布局
        content_layout.addWidget(self.llm_config_card)
        content_layout.addWidget(self.prompt_config_card)
        content_layout.addWidget(self.business_hours_card)
        content_layout.addWidget(self.oss_config_card)
        content_layout.addWidget(self.kb_config_card)
        content_layout.addWidget(self.db_config_card)
        content_layout.addStretch()

        # 设置容器样式
        content_container.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border: none;
            }
        """)

        scroll_area.setWidget(content_container)

        return scroll_area

    def loadConfig(self):
        """从config模块加载配置"""
        try:
            # 从配置模块获取各个配置项
            loaded_config = {
                "llm": {
                    "api_base": config.get("llm.api_base", "https://ark.cn-beijing.volces.com/api/v3"),
                    "api_key": config.get("llm.api_key", ""),
                    "model_name": config.get("llm.model_name", ""),
                    "supports_vision": config.get("llm.supports_vision", False),
                },
                "prompt": {
                    "instructions": config.get("prompt.instructions", [])
                },
                "business_hours": {
                    "start": config.get("business_hours.start", "08:00"),
                    "end": config.get("business_hours.end", "23:00")
                },
                "oss": {
                    "access_key_id": config.get("oss.access_key_id", ""),
                    "access_key_secret": config.get("oss.access_key_secret", ""),
                    "endpoint": config.get("oss.endpoint", "oss-cn-shenzhen.aliyuncs.com"),
                    "bucket": config.get("oss.bucket", ""),
                },
                "knowledge_base": {
                    "embedding": {
                        "provider": config.get("knowledge_base.embedding.provider", "openai"),
                        "model_name": config.get("knowledge_base.embedding.model_name", ""),
                        "api_key": config.get("knowledge_base.embedding.api_key", ""),
                        "api_base": config.get("knowledge_base.embedding.api_base", ""),
                        "dimension": config.get("knowledge_base.embedding.dimension", 1536),
                    },
                    "reranker": {
                        "provider": config.get("knowledge_base.reranker.provider", "local"),
                        "model_name": config.get("knowledge_base.reranker.model_name", ""),
                        "api_key": config.get("knowledge_base.reranker.api_key", ""),
                        "api_base": config.get("knowledge_base.reranker.api_base", ""),
                    },
                    "chunk_size": config.get("knowledge_base.chunk_size", 500),
                    "chunk_overlap": config.get("knowledge_base.chunk_overlap", 50),
                },
                "db_path": config.get("db_path", "./temp/channel_shop.db"),
            }

            # 验证并设置配置
            self._validateAndSetConfig(loaded_config)
            self.logger.info("配置加载成功")

        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
            QMessageBox.warning(self, "加载失败", f"加载配置失败：{str(e)}")
            self._loadDefaultConfig()

    def _loadDefaultConfig(self):
        """加载默认配置"""
        # 使用 config_base 作为基础配置
        default_config = config_base.copy()

        # 补充 UI 特定的默认值（当 config_base 中字段为空时）
        if not default_config.get("llm", {}).get("api_base"):
            default_config["llm"] = default_config.get("llm", {})
            default_config["llm"]["api_base"] = "https://ark.cn-beijing.volces.com/api/v3"
        if not default_config.get("llm", {}).get("model_name"):
            default_config["llm"]["model_name"] = "doubao-seed-1-6-flash-250828"

        self._validateAndSetConfig(default_config)
        self.logger.info("已加载默认配置")

    def _validateAndSetConfig(self, config_data):
        """验证并设置配置"""
        # 确保必要的字段存在
        validated_config = {
            "llm": config_data.get("llm", {
                "api_base": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "",
                "model_name": "doubao-seed-1-6-flash-250828"
            }),
            "prompt": config_data.get("prompt", {
                "instructions": []
            }),
            "business_hours": config_data.get("business_hours", {"start": "08:00", "end": "23:00"})
        }

        # 验证business_hours格式
        business_hours = validated_config["business_hours"]
        if not isinstance(business_hours, dict):
            business_hours = {"start": "08:00", "end": "23:00"}
            validated_config["business_hours"] = business_hours

        if "start" not in business_hours:
            business_hours["start"] = "08:00"
        if "end" not in business_hours:
            business_hours["end"] = "23:00"

        # 设置到界面
        self.llm_config_card.setConfig(validated_config.get("llm", {}))
        self.prompt_config_card.setConfig(validated_config.get("prompt", {}))
        self.business_hours_card.setConfig({"business_hours": validated_config.get("business_hours", {})})
        self.oss_config_card.setConfig(validated_config.get("oss", {}))
        self.kb_config_card.setConfig(validated_config.get("knowledge_base", {}))
        self.db_config_card.setConfig(validated_config)

    def onSaveConfig(self):
        """保存配置到config模块"""
        try:
            # 获取各配置卡片的配置
            llm_config = self.llm_config_card.getConfig()
            prompt_config = self.prompt_config_card.getConfig()
            business_config = self.business_hours_card.getConfig()
            oss_config = self.oss_config_card.getConfig()
            kb_config = self.kb_config_card.getConfig()
            db_config = self.db_config_card.getConfig()

            # 合并配置为新的结构
            new_config = {
                "llm": llm_config,
                "prompt": prompt_config,
                "business_hours": business_config.get("businessHours", {"start": "08:00", "end": "23:00"}),
                "oss": oss_config,
                "knowledge_base": kb_config,
                "db_path": db_config.get("db_path", "") or config.get("db_path", ""),
            }

            # 验证 LLM 必填项
            if not llm_config.get("api_key"):
                QMessageBox.warning(self, "配置错误", "请输入LLM API Key！")
                return
            if not llm_config.get("model_name"):
                QMessageBox.warning(self, "配置错误", "请输入LLM模型名称！")
                return

            # 验证时间设置
            start_time = self.business_hours_card.start_time_picker.getTime()
            end_time = self.business_hours_card.end_time_picker.getTime()

            if start_time >= end_time:
                QMessageBox.warning(self, "时间设置错误", "开始时间必须早于结束时间！")
                return

            # 使用config模块保存配置
            config.update(new_config, save=True)

            self.logger.info("配置保存成功")

            # 显示成功消息
            InfoBar.success(
                title="保存成功",
                content="配置已保存！",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时发生错误：{str(e)}")

    def onResetConfig(self):
        """重置配置"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有配置吗？\n这将重新加载配置文件中的原始设置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 使用config模块重新加载配置文件
                config.reload()
                self.loadConfig()
                self.logger.info("配置已重置")

                InfoBar.success(
                    title="重置成功",
                    content="配置已重置为配置文件中的设置！",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                self.logger.error(f"重置配置失败: {e}")
                QMessageBox.critical(self, "重置失败", f"重置配置失败：{str(e)}")


