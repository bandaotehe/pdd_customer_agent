# Customer-Agent

电商 AI 客服桌面应用，基于 PyQt6 + 自研 Agent 框架，集成大语言模型实现智能自动回复。当前支持拼多多平台。

> 本项目基于 [JC0v0/Customer-Agent](https://github.com/JC0v0/Customer-Agent) 二次开发，感谢原作者 [JC0v0](https://github.com/JC0v0) 的开源贡献。

---

## 目录

- [功能特性](#功能特性)
- [AI Agent 工具集](#ai-agent-工具集)
- [知识库系统](#知识库系统)
- [通知系统](#通知系统)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [配置](#配置)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [构建](#构建)

---

## 功能特性

### AI 客服核心

- **自研 Agent 框架**：不依赖 LangChain/Agno，自主实现多轮工具调用循环（最多 5 轮）
- **6 个 Agent 工具**：商品查询、知识搜索、商品列表、发送商品卡片、发送产品图片、会话转接
- **工具并行执行**：多工具调用并发执行，提升响应速度
- **上下文压缩**：超过 token 窗口 70% 时 LLM 自动摘要，保留最近 10 条消息
- **多模态理解**：支持用户发送图片/视频，下载后转 base64 发给视觉模型
- **自动参数注入**：LLM 未提供的参数（shop_id、user_id 等）从上下文自动填充
- **售前专用定位**：AI 专注售前咨询，涉及售后（退换货、退款、投诉等）自动转接人工，话术模拟真人同事转接不暴露 AI 身份

### 消息处理管道

- **异步 FIFO 队列**：`asyncio.Queue` + 信号量并发控制
- **处理器链**：关键词检测 → AI 回复 → 兜底处理
- **2.5 秒批次窗口**：同一客户短时间内的多条消息合并后统一处理，支持文本+图片/视频联合理解
- **消息预处理**：JSON 安全解析、文本清洗、长度限制
- **MD5 去重**：防止重复消息多次处理
- **关键词转人工**：检测到"退款""投诉""转人工"等关键词后，直接调用拼多多会话转接 API，转接失败自动发安抚消息

### 渠道集成（拼多多）

- **WebSocket 实时通信**：长连接接收消息推送，支持 12+ 种消息类型
- **自动重连**：断线后指数退避重连（2s → 60s）+ 随机抖动
- **心跳检测**：30 秒间隔 Ping，连续 3 次失败标记异常
- **Playwright 自动化登录**：浏览器提取 Cookie，会话过期自动续期
- **API 封装**：发送文本/图片/商品卡片、获取商品列表/详情、会话转接、客服状态设置
- **API 自动重试**：请求失败指数退避重试，session 过期自动重新登录

### 知识库系统

- **三库架构**：产品知识（LLM 自动提取）+ 客服知识（人工录入 FAQ/政策）+ 自定义知识（用户上传文档）
- **混合检索管道**：分块 → 向量嵌入 → ChromaDB 向量检索 + BM25 关键词检索 → RRF 融合 → Cross-Encoder 重排序
- **回退模式**：向量索引不可用时自动降级为 jieba 分词 + SQL LIKE 传统检索
- **商品自动同步**：从拼多多 API 拉取商品列表，调用多模态 LLM（商品图片 + 文本）提取结构化产品知识，自动写入知识库和向量索引
- **知识库标签**：预设标签体系（物流 / 支付 / 商品规格 / 优惠券 / 会员 / 发货时间 / 退换货），支持筛选
- **批量导入**：支持 Excel / Word / PDF / TXT 文件批量导入

### 桌面 UI

- **PyQt6 + Fluent Design**：微软 Fluent Design 风格
- **懒加载**：视图延迟加载，窗口快速启动
- **5 个主导航页**：
  - **数据统计**：KPI 卡片（今日消息/会话/转接/错误）+ 7 日趋势图 + 告警列表
  - **账号与客服**：双标签页（账号管理 + 自动回复控制）
  - **会话管理**：三层导航（店铺列表 → 会话列表 → 聊天详情），滑动动画切换，消息气泡 + 转接确认气泡
  - **知识管理**：四标签页（产品知识 / 客服知识 / 自定义知识 / 关键词管理）
  - **日志管理**：实时流式日志 + 级别过滤 + Text/JSON/CSV 导出
  - 底部：**设置**（LLM / Prompt / 营业时间 / OSS / 知识库参数）
- **系统托盘**：图标常驻，气泡消息，双击恢复窗口，右键菜单（显示窗口 / 退出）
- **统一主题**：50+ 色值常量 + 微软雅黑字体体系 + 间距规范

### 基础设施

- **DI 容器**：singleton / transient / scoped 三种生命周期，向后兼容旧式全局变量
- **连接池**：数据库连接池管理
- **线程安全配置**：Pydantic 校验 + 原子化保存（临时文件 + 重命名，避免写中断损坏）
- **日志系统**：Loguru 多 sink（控制台 + 文件轮转）+ BusinessLogger 结构化日志 + UILogHandler 实时推送到 UI
- **WebSocket 资源管理**：统一注册/注销，优雅关闭

---

## AI Agent 工具集

| 工具 | 参数 | 用途 |
|------|------|------|
| `get_product_knowledge` | goods_id, shop_id | 查询商品详细知识（成分、规格、用法、功效、价格） |
| `search_customer_service_knowledge` | query, shop_id | 搜索客服知识库（物流、发货、FAQ 等） |
| `get_shop_products` | shop_id, user_id | 获取店铺商品列表，支持分页 |
| `send_goods_link` | recipient_uid, goods_id, shop_id, user_id | 向用户发送商品卡片 |
| `send_product_image` | goods_id, recipient_uid, shop_id, user_id | 向用户发送产品说明书图片 |
| `transfer_conversation` | shop_id, user_id, recipient_uid | 转接会话给售后专员 |

Agent 循环流程：

```
用户消息 → 加载历史 → 判断是否需压缩 → 构建消息列表（System Prompt + 历史 + 当前消息）
→ LLM 调用 → 解析 tool_calls → 并行执行工具 → 结果回传
→ 循环（最多 5 轮）→ 返回最终回复 → 持久化到数据库
```

---

## 知识库系统

### 检索管道

```
用户问题
    │
    ▼
  分块（递归字符分割，500 字符/块，50 字符重叠）
    │
    ▼
  嵌入（OpenAI text-embedding-3-small / 本地 sentence-transformers）
    │
    ├──────────────┬──────────────────┐
    ▼              ▼                  ▼
  ChromaDB      BM25Okapi          (可按需扩展)
  向量检索      jieba 关键词检索
    │              │
    └──────┬───────┘
           ▼
     RRF 融合（k=60, alpha=0.5）
           │
           ▼
     Cross-Encoder 重排序（BAAI/bge-reranker-v2-m3）
           │
           ▼
     返回最佳匹配结果
```

### 三库说明

| 知识库 | 数据来源 | 典型内容 |
|--------|----------|----------|
| 产品知识 | LLM 从拼多多商品数据中自动提取 | 品牌、成分、规格、功效、用法、价格 |
| 客服知识 | 人工在 UI 中录入 | 物流政策、发货时间、退换货规则、FAQ |
| 自定义知识 | 用户上传文档（Word/Excel/PDF/TXT） | 产品手册、行业规范、用药指南 |

---

## 通知系统

当客户触发转人工时，系统通过 4 层机制提醒管理员：

| 层级 | 机制 | 场景 |
|------|------|------|
| InfoBar 弹窗 | 右上角弹出警告卡片（需手动关闭） | 窗口可见时 |
| 侧边栏红点 | "会话管理"导航项显示红色数字角标 | 管理员在别的页签 |
| 系统托盘气泡 | Windows 通知区域弹出（5 秒消失） | 窗口最小化到托盘 |
| 任务栏闪烁 | 任务栏图标持续闪烁 | 窗口最小化到任务栏 |

点击"会话管理"页签后红点角标自动清除。

---

## 环境要求

- Python >= 3.11
- Windows 操作系统

---

## 快速开始

### 方式一：开箱即用（推荐）

下载完整压缩包，解压后直接运行，无需安装 Python 或任何配置：

> **[下载完整压缩包]()** ← 链接待补充

解压后双击 `AgentCustomer.exe` 即可启动。压缩包已内置 Python 运行时、Playwright 浏览器、默认配置，开箱即用。

### 方式二：源码运行

```bash
# 安装依赖
uv sync

# 启动
python app.py
```

首次运行自动生成 `config.json`，填入 LLM API 密钥后即可使用。

---

## 配置

### config.json

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `llm.model_name` | string | 模型名称 |
| `llm.api_key` | string | API 密钥 |
| `llm.api_base` | string | API 地址（OpenAI 兼容） |
| `llm.supports_vision` | bool | 是否支持图片/视频 |
| `prompt.instructions` | string[] | AI 客服指令，注入 System Prompt |
| `business_hours.start` | string | 营业开始时间（HH:MM） |
| `business_hours.end` | string | 营业结束时间（HH:MM） |
| `db_path` | string | SQLite 数据库路径 |
| `knowledge_base.embedding.provider` | string | 嵌入模型提供商（openai / local） |
| `knowledge_base.embedding.model_name` | string | 嵌入模型名称 |
| `knowledge_base.embedding.api_key` | string | 嵌入 API 密钥（为空则复用 llm.api_key） |
| `knowledge_base.embedding.dimension` | int | 嵌入向量维度 |
| `knowledge_base.reranker.provider` | string | 重排序提供商（api / local） |
| `knowledge_base.reranker.model_name` | string | 重排序模型名称 |
| `knowledge_base.vector_db.persist_directory` | string | ChromaDB 持久化目录 |
| `knowledge_base.hybrid_search_alpha` | float | 混合检索权重（1=纯向量, 0=纯BM25） |
| `knowledge_base.chunk_size` | int | 分块大小（字符） |
| `knowledge_base.chunk_overlap` | int | 分块重叠（字符） |
| `oss.access_key_id` | string | 阿里云 OSS AccessKey ID |
| `oss.access_key_secret` | string | 阿里云 OSS AccessKey Secret |
| `oss.endpoint` | string | OSS Endpoint |
| `oss.bucket` | string | OSS Bucket 名称 |

### Agent 参数（agent_config.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `token_window` | 131072 | Token 窗口大小 |
| `compress_ratio` | 0.7 | 上下文压缩触发阈值 |
| `retain_count` | 10 | 压缩时保留的最近消息数 |
| `max_loops` | 5 | Agent 最大工具调用轮数 |
| `temperature` | 0.3 | LLM 温度 |

---

## 项目结构

```
Customer-Agent/
├── Agent/                              # AI Agent 模块（自研框架）
│   ├── bot.py                          #   Bot 抽象基类
│   └── CustomerAgent/
│       ├── custom/                     #   Agent 核心
│       │   ├── customer_agent.py       #     Agent 循环（LLM→工具→回传→循环）
│       │   ├── llm_client.py           #     OpenAI 兼容 LLM 客户端
│       │   ├── message_builder.py      #     System Prompt 构建 + 商品列表注入
│       │   ├── session_manager.py      #     会话持久化 + Token 估算
│       │   ├── tool_executor.py        #     工具并行执行引擎
│       │   ├── tool_decorator.py       #     @agent_tool 装饰器 + 全局注册表
│       │   ├── agent_config.py         #     Agent 配置
│       │   └── media_utils.py          #     图片下载 → base64
│       └── tools/                      #   6 个 Agent 工具
│
├── Channel/                            # 渠道集成
│   └── pinduoduo/
│       ├── pdd_channel.py              #   PDDChannel（Mixin 组合）
│       ├── pdd_login.py                #   Playwright 自动化登录
│       ├── pdd_message.py              #   消息解析（12+ 类型）
│       ├── core/                       #   连接/生命周期/状态 Mixin
│       └── utils/API/                  #   拼多多 API 封装
│
├── Message/                            # 消息处理管道
│   ├── core/                           #   队列 + 消费者 + 处理器基类
│   ├── handlers/                       #   关键词 / AI 回复 / 预处理
│   └── models/                         #   消息模型
│
├── services/                           # 知识库升级核心
│   ├── chunking_service.py             #   递归字符分割
│   ├── embedding_service.py            #   嵌入服务（API / 本地）
│   ├── vector_store.py                 #   ChromaDB 封装
│   ├── bm25_index.py                   #   BM25 + jieba
│   ├── hybrid_retriever.py             #   向量 + BM25 + RRF 融合
│   ├── reranker_service.py             #   Cross-Encoder 重排序
│   ├── vector_index_sync.py            #   SQL → 向量索引同步
│   └── custom_knowledge_service.py     #   自定义知识 CRUD
│
├── database/                           # 数据层
│   ├── models.py                       #   SQLAlchemy ORM 模型
│   ├── db_manager.py                   #   数据库管理器
│   ├── knowledge_service.py            #   知识库服务（混合检索 + 回退）
│   ├── product_sync.py                 #   商品同步（API + LLM 提取）
│   └── connection_pool.py              #   连接池
│
├── bridge/                             # 桥接类型
│   ├── context.py                      #   Context / ContextType / ChannelType
│   └── reply.py                        #   Reply / ReplyType
│
├── core/                               # 核心基础设施
│   ├── di_container.py                 #   DI 容器
│   ├── connection_status.py            #   连接状态管理
│   ├── cache.py                        #   缓存（LRU/FIFO/TTL/LFU）
│   └── service_providers.py            #   向后兼容代理
│
├── ui/                                 # PyQt6 桌面界面
│   ├── main_ui.py                      #   主窗口（导航 + 系统托盘 + 通知）
│   ├── session_ui.py                   #   会话管理（三层导航 + 动画）
│   ├── statistics_ui.py                #   数据统计（KPI + 趋势）
│   ├── account_service_ui.py           #   账号与客服
│   ├── Knowledge_ui.py                 #   知识管理（四标签页）
│   ├── setting_ui.py                   #   设置
│   ├── log_ui.py                       #   日志查看器
│   ├── keyword_ui.py                   #   关键词管理
│   ├── user_ui.py                      #   账号管理
│   ├── error_notifier.py               #   全局信号总线
│   ├── file_import_dialog.py           #   批量导入
│   ├── theme.py                        #   主题系统
│   ├── widgets/                        #   通用组件
│   └── auto_reply/                     #   自动回复（QThread）
│
├── utils/                              # 工具模块
│   ├── logger_loguru.py                #   日志（Loguru + BusinessLogger）
│   ├── oss_client.py                   #   阿里云 OSS
│   ├── async_helper.py                 #   异步工具
│   └── ...
│
├── scripts/                            # 构建脚本
├── config.py                           # Pydantic 配置管理
├── config.json                         # 运行时配置
├── pyproject.toml                      # 项目元数据
└── app.py                              # 入口
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| UI 框架 | PyQt6 + pyqt6-fluent-widgets |
| AI Agent | 自研框架 + OpenAI 兼容 API |
| 向量数据库 | ChromaDB |
| 关键词检索 | BM25Okapi + jieba |
| 重排序 | Cross-Encoder（BAAI/bge-reranker-v2-m3） |
| 关系数据库 | SQLAlchemy + SQLite |
| 异步通信 | asyncio + websockets + aiohttp |
| 浏览器自动化 | Playwright |
| 文档解析 | pypdf + python-docx + openpyxl + xlrd |
| 配置校验 | Pydantic |
| Token 统计 | tiktoken |
| 日志 | Loguru |
| 云存储 | 阿里云 OSS |
| 打包 | PyInstaller |

---

## 构建

```bash
# Windows 可执行文件
python scripts/build_win_exe.py --clean

# 完整构建（含 NSIS 安装包脚本）
python scripts/build_exe.py --mode release
```

产物位于 `dist/AgentCustomer/`，Playwright 浏览器二进制自动打包。

---

## License

MIT

---

## 致谢

本项目基于 [JC0v0/Customer-Agent](https://github.com/JC0v0/Customer-Agent) 二次开发，感谢 [JC0v0](https://github.com/JC0v0) 的开源贡献。
