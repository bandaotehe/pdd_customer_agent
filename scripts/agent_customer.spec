# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Agent-Customer
生成命令: pyinstaller scripts/agent_customer.spec
"""

import sys
import os
from pathlib import Path

block_cipher = None

# 项目根目录（spec 文件位于 scripts/ 目录，上两级为项目根目录）
if '__file__' in globals():
    _spec_dir = Path(os.path.abspath(__file__)).parent
    PROJECT_ROOT = _spec_dir.parent
elif len(sys.argv) > 0:
    # fallback: 从命令行参数推导
    PROJECT_ROOT = Path(sys.argv[0]).resolve().parent.parent
else:
    # last fallback: 从 cwd 推导
    PROJECT_ROOT = Path.cwd()

# ================================
# 基础配置
# ================================
a = Analysis(
    [str(PROJECT_ROOT / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "icon" / "icon.ico"), "icon"),
        (str(PROJECT_ROOT / "config.json"), "."),
        (str(PROJECT_ROOT / "anti_content.js"), "."),
        (str(PROJECT_ROOT / "generate_anti_content.html"), "."),
    ],
    hiddenimports=[
        # === PyQt6 & Fluent Widgets ===
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "qfluentwidgets",
        "qfluentwidgets.common",
        "qfluentwidgets.components",
        "qfluentwidgets.navigation",
        "qfluentwidgets.window",
        # === AI / LLM ===
        "openai",
        "openai._base",
        "openai._models",
        "openai._client",
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
        # === 数据库 ===
        "sqlalchemy",
        "sqlalchemy.orm",
        "sqlalchemy.sql",
        "sqlalchemy.dialects.sqlite",
        # === 向量存储 ===
        "chromadb",
        "chromadb.config",
        "chromadb.api",
        "chromadb.db",
        "chromadb.ingest",
        "chromadb.telemetry",
        "chromadb.utils",
        "chromadb.utils.embedding_functions",
        "onnxruntime",
        # === 搜索 / 分词 ===
        "jieba",
        "jieba.analyse",
        "jieba.posseg",
        "rank_bm25",
        # === 日志 ===
        "loguru",
        "loguru._logger",
        # === Web / 网络 ===
        "websockets",
        "websockets.client",
        "websockets.server",
        "aiohttp",
        "aiohttp.client",
        "aiohttp.web",
        "aiohttp.websocket",
        "requests",
        "urllib3",
        "charset_normalizer",
        # === 浏览器自动化 ===
        "playwright",
        "playwright._impl",
        "playwright.async_api",
        # === 数据处理 ===
        "pandas",
        "pandas._libs",
        "numpy",
        "numpy.core",
        "numpy._core",
        "openpyxl",
        "openpyxl.cell",
        "openpyxl.workbook",
        "pypdf",
        "docx",
        "docx.document",
        "docx.oxml",
        # === 图像 ===
        "PIL",
        "PIL._imaging",
        "cv2",
        "cv2.cv2",
        # === 异步 ===
        "asyncio",
        "aiofiles",
        # === 工具类 ===
        "pydantic",
        "pydantic.base",
        "pydantic.fields",
        "pydantic.dataclasses",
        "pydantic.v1",
        "pydantic.v1.error_messages",
        "pydantic.v1.fields",
        "volcengine",
        "volcengine.base",
        "volcengine.viking_knowledgebase",
        "volcengine.viking_knowledgebase.Collection",
        "volcengine.viking_knowledgebase.Doc",
        # === rich / huggingface_hub (chromadb deps) ===
        "rich",
        "rich.console",
        "rich.table",
        "rich.progress",
        "huggingface_hub",
        "tokenizers",
        "tenacity",
        "overrides",
        "pyyaml",
        "orjson",
        # === OSS ===
        "oss2",
        # === httpx / httpcore ===
        "httpx",
        "httpcore",
        # === 项目内部模块 ===
        "config",
        "core.di_container",
        "core.connection_status",
        "core.cache",
        "core.base_service",
        "database.db_manager",
        "database.models",
        "database.connection_pool",
        "database.knowledge_service",
        "database.product_sync",
        "bridge.context",
        "bridge.reply",
        "Message.message",
        "Message.core.queue",
        "Message.core.consumer",
        "Message.core.handlers",
        "Message.handlers.base",
        "Message.handlers.ai_handler",
        "Message.handlers.keyword_handler",
        "Message.handlers.preprocessor",
        "Agent.bot",
        "Agent.CustomerAgent.custom.customer_agent",
        "Agent.CustomerAgent.custom.agent_config",
        "Agent.CustomerAgent.custom.tool_decorator",
        "Agent.CustomerAgent.custom.tool_executor",
        "Agent.CustomerAgent.custom.session_manager",
        "Agent.CustomerAgent.custom.message_builder",
        "Agent.CustomerAgent.custom.llm_client",
        "Agent.CustomerAgent.tools",
        "Agent.CustomerAgent.tools.get_product_list",
        "Agent.CustomerAgent.tools.get_product_knowledge",
        "Agent.CustomerAgent.tools.search_customer_service_knowledge",
        "Agent.CustomerAgent.tools.send_goods_link",
        "Agent.CustomerAgent.tools.move_conversation",
        "Channel.channel",
        "Channel.pinduoduo.pdd_channel",
        "Channel.pinduoduo.pdd_message",
        "Channel.pinduoduo.pdd_login",
        "Channel.pinduoduo.core.pdd_connection",
        "Channel.pinduoduo.core.pdd_message_handler",
        "Channel.pinduoduo.core.pdd_status",
        "Channel.pinduoduo.utils.base_request",
        "Channel.pinduoduo.utils.API.get_token",
        "Channel.pinduoduo.utils.API.send_message",
        "Channel.pinduoduo.utils.API.get_shop_info",
        "Channel.pinduoduo.utils.API.Set_up_online",
        "Channel.pinduoduo.utils.API.product_manager",
        "Channel.pinduoduo.utils.API.get_user_info",
        # === 新服务模块 ===
        "services",
        "services.chunking_service",
        "services.embedding_service",
        "services.vector_store",
        "services.bm25_index",
        "services.hybrid_retriever",
        "services.reranker_service",
        "services.vector_index_sync",
        "services.custom_knowledge_service",
        # === 新 UI 模块 ===
        "ui",
        "ui.auto_reply_ui",
        "ui.auto_reply.manager",
        "ui.auto_reply.threads",
        "ui.auto_reply.card",
        "ui.auto_reply.ui",
        "ui.keyword_ui",
        "ui.user_ui",
        "ui.log_ui",
        "ui.setting_ui",
        "ui.Knowledge_ui",
        "ui.session_ui",
        "ui.statistics_ui",
        "ui.file_import_dialog",
        "ui.error_notifier",
        "ui.main_ui",
        # === 工具类 ===
        "utils.logger_loguru",
        "utils.logger_config",
        "utils.logging_context",
        "utils.resource_manager",
        "utils.path_utils",
        "utils.runtime_path",
        "utils.async_helper",
        "utils.encoding_helper",
        "utils.file_validator",
        "utils.volcengine_models",
        # === 避免 pydantic 冲突 ===
        "pydantic.errors",
        "pydantic.main",
        "pydantic.schema",
        "pydantic.types",
        "pydantic.validators",
        "pydantic.class_validators",
        "pydantic.config",
        "pydantic.parse",
        "pydantic.tools",
        "pydantic.utils",
        # === 避免 importlib 静默失败 ===
        "importlib",
        "importlib.util",
        "importlib.abc",
        "importlib.metadata",
        # === jsonschema ===
        "jsonschema",
        "jsonschema_specifications",
        # === certifi / charset / 网络 ===
        "certifi",
        "charset_normalizer",
    ],
    hookspath=[],
    hooksconfig={},
    keys=block_cipher,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # Windows 下关闭 UPX（兼容性更好）
    console=False,        # 不显示控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ================================
# 生成 PYZ（Python 库）
# ================================
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ================================
# 生成 EXE（文件夹模式，兼容 Playwright）
# ================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AgentCustomer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "icon" / "icon.ico"),
    version="",
    description="电商AI客服助手",
    product_name="Agent-Customer",
    product_version="0.1.0",
    company_name="",
    legal_copyright="",
   RequestedExecutionLevel="asInvoker",
    env=[
        ("PYTHONHOME", str(Path(sys.exec_prefix))),
    ],
)

# 收集所有文件到 dist 目录
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AgentCustomer",
)
