# 知识库问答模块 — 技术架构文档

> 版本：v1.2 ｜ 更新日期：2026-05-14 ｜ 对应分支：`main`

---

## 1. 整体流程

```
用户提问 → 关键词检测（转人工分流）→ AI 回复处理器
  → MessageBuilder 构建消息上下文（系统提示 + 工具声明 + 商品列表 + 会话历史）
  → LLM 推理决策：是否需要查询知识库？
    ├── 是 → ToolExecutor 并行执行知识工具
    │         ├── get_product_knowledge()   → jieba 分词 + SQL LIKE 检索
    │         └── search_customer_service_knowledge() → jieba 分词 + SQL LIKE 检索
    │       → 检索结果回传 LLM → 生成最终回答
    └── 否 → LLM 直接生成回答
  → 保存消息到会话历史 → 通过拼多多 API 发送回复给用户
```

---

## 2. 核心流程说明

### 2.1 离线流程（知识入库）

系统采用 **LLM 辅助提取 + 人工录入** 的混合建库方式，不含传统文档切片/向量化步骤。

```
┌─────────────────────────────────────────────────────┐
│ 来源 A：产品知识（LLM 自动提取）                       │
│                                                       │
│  拼多多商品 API                                        │
│     │                                                  │
│     ▼                                                  │
│  ProductManager.get_product_list() 分页拉取商品列表      │
│     │                                                  │
│     ├── 阶段 1：快速入库                                 │
│     │   商品名称、价格、缩略图 → product_knowledge 表      │
│     │   extracted_content = NULL（待提取）               │
│     │                                                  │
│     ├── 阶段 2：LLM 提取（asyncio.Semaphore(3) 并发）    │
│     │   │                                              │
│     │   ▼                                              │
│     │  AsyncOpenAI (Doubao-pro-32k) + 商品图片（多模态）  │
│     │   │                                              │
│     │   ▼                                              │
│     │  结构化 JSON 输出：                                │
│     │    brand, origin, ingredients, spec_quantity,     │
│     │    suitable_age, shelf_life, description,         │
│     │    key_points, usage, faq                        │
│     │   │                                              │
│     │   ▼                                              │
│     │  写入 extracted_content 字段                       │
│     │                                                  │
│     └── LLM 失败时降级为 _format_basic_info() 兜底       │
│                                                       │
├─────────────────────────────────────────────────────┤
│ 来源 B：客服知识（人工录入 / Excel 批量导入）             │
│                                                       │
│  人工通过 UI 逐条添加 或 批量导入 Excel                    │
│     │                                                  │
│     ▼                                                  │
│  customer_service_knowledge 表                         │
│    title, content, tags（逗号分隔）, enabled             │
│    tags 预设：物流/售后/支付/商品规格/优惠券/会员/        │
│             发货时间/退换货                              │
└─────────────────────────────────────────────────────┘
```

**关键点：**
- **不含文档切片（chunking）**：知识以结构化字段或单条记录为单位存储，非长文档分块
- **不含向量化（embedding）**：不调用嵌入模型，不构建向量索引
- **索引仅依赖 SQLite B-Tree** 和联合唯一约束 `(shop_id, goods_id)`
- 产品同步由 `database/product_sync.py` 中的 `SyncWorker`（QThread）在后台执行

### 2.2 在线流程（查询与回答）

```
用户消息到达
     │
     ▼
Context 对象构建（含 shop_id, from_uid, channel_type 等）
     │
     ▼
KeywordDetectionHandler（优先级最高，拦截转人工关键词）
     │ 匹配 → 回复确认消息 + 通知管理员
     │ 未匹配 →
     ▼
AIReplyHandler
     │
     ▼
CustomerAgent.async_reply()
     │
     ├── MessageBuilder.build_dependencies()  提取依赖（shop_id, user_id）
     ├── MessageBuilder.build_messages()      构建消息列表
     │       ├── 系统提示（含工具声明 + 商品列表注入）
     │       ├── 历史消息（从 SQLite 加载，token 超阈值时自动压缩）
     │       └── 当前用户消息
     │
     ▼
LLM 调用（AsyncOpenAI，response_format="json_object" 强制 JSON 输出）
     │
     ├── 有 tool_calls →
     │       ToolExecutor.execute_parallel() 并行调用工具
     │       结果回传 LLM → 循环（最多 5 轮）
     │
     └── 无 tool_calls → 提取最终回答
     │
     ▼
发送回复（拼多多 HTTP API）
```

**检索细节（`knowledge_service.search_knowledge()`）：**

```
query + shop_id 输入
     │
     ▼
_resolve_shop_id()：将拼多多原始 shop_id 映射到内部数据库 ID
     │
     ├── 有 goods_id → 精确匹配 product_knowledge.goods_id
     │
     ├── 有关键词 → jieba.cut_for_search(query) 分词
     │       ├── 过滤长度 < 2 的词
     │       └── 对每个词做 SQL LIKE 查询：
     │             产品表：goods_name LIKE '%词%' OR extracted_content LIKE '%词%'
     │             客服表：title LIKE '%词%' OR content LIKE '%词%'
     │           多个词用 OR 组合
     │
     └── 无关键词 → 返回最新 N 条记录（时间降序）
     │
     ▼
format_search_result() 格式化输出：
     产品知识每字段截断 500 字符 | 客服知识每条截断 300 字符
     以 Markdown 格式拼合为纯文本，回传 LLM
```

---

## 3. 技术实现细节

### 3.1 知识库类型

| 类型 | 存储表 | 数据结构 | 来源 |
|------|--------|----------|------|
| 产品知识（结构化） | `product_knowledge` | 半结构化 JSON 文本（`extracted_content` TEXT 字段存储 LLM 输出的 JSON） | LLM 多模态提取 |
| 客服知识（非结构化） | `customer_service_knowledge` | 自由文本 + 标签（`title`, `content`, `tags` 逗号分隔） | 人工录入 / Excel 批量导入 |

当前**不支持**文件上传、PDF 解析、URL 抓取等文档摄入方式。

### 3.2 检索方式

**关键词检索**（基于 jieba 分词 + SQL LIKE），非向量检索，非混合检索。

- 分词引擎：`jieba.cut_for_search()`（搜索引擎模式，对长词做细粒度切分）
- 过滤策略：丢弃长度 < 2 的单字词
- 匹配逻辑：多词 OR 组合，多字段 UNION
- 排序：数据库默认顺序（无 TF-IDF / BM25 相关性评分）
- 无重排（rerank）阶段

### 3.3 嵌入模型与向量数据库

**无。** 当前系统不使用嵌入模型或向量数据库。

`utils/runtime_path.py:155-163` 中存在 `get_vector_db_path()` 和 `get_contents_db_path()` 函数定义，但全代码库无调用点，属于未启用的预留扩展位。

### 3.4 大语言模型（LLM）及其调用方式

| 环节 | 模型 | 调用方式 | 关键参数 |
|------|------|----------|----------|
| 产品知识提取 | Doubao-pro-32k（火山引擎） | `AsyncOpenAI` 客户端，兼容 OpenAI SDK | `response_format={"type": "json_object"}`，支持多模态（传入商品图片 URL） |
| Agent 对话 | 由 `llm_client.py` 统一管理，支持多 provider | `AsyncOpenAI`，OpenAI function-calling 格式 | temperature 0.3，max_tokens 4096，支持工具调用 |
| 上下文压缩 | 同上 Agent 模型 | `llm_callable` 注入 `SessionManager.compress_history()` | 摘要生成，非对话用途 |

**LLM 客户端架构（`llm_client.py`）：**
- 基于 `AsyncOpenAI`（OpenAI 兼容协议）
- 支持 Provider 抽象：火山引擎、DeepSeek 等通过 `api_key` + `base_url` 切换
- 支持 prompt caching（通过 Anthropic/OpenAI 原生缓存标记）

**工具调用方式（Agent 循环）：**
1. 系统提示中硬编码工具说明（`message_builder.py:59-87`）
2. 工具通过 `@agent_tool` 装饰器注册到全局 `TOOL_REGISTRY`
3. `get_tools_for_llm()` 将注册的工具转换为 OpenAI function-calling JSON Schema
4. LLM 返回 `tool_calls` 后，`ToolExecutor.execute_parallel()` 并行执行
5. 执行结果追加到消息列表，回传 LLM 继续推理
6. 最多 5 轮循环，防止无限工具调用

### 3.5 工程实践

| 实践 | 实现方式 | 位置 |
|------|----------|------|
| 缓存 | 商品列表缓存在内存（`ProductCardList` 的 `_item_cache`），会话历史缓存于 SQLite | `session_manager.py`、Agent 聊天记录表 |
| 限流 | 产品同步阶段 2 使用 `asyncio.Semaphore(3)` 限制 LLM 并发，分页间隔 200ms | `product_sync.py:292-303` |
| 日志 | 全模块使用 `loguru`，每个模块独立 logger（如 `get_logger("KnowledgeService")`） | 各模块顶部 |
| 错误降级 | LLM 提取失败时调用 `_format_basic_info()` 输出基础模板；AI 回复失败时走 `_handle_fallback()` 兜底回复 | `product_sync.py:462-480`、`ai_handler.py:172-193` |
| 上下文压缩 | 当历史 token 超过窗口 70% 时触发，LLM 摘要旧消息 + 保留最近 N 条 | `session_manager.py:324-401` |
| 依赖注入 | `core/di_container.py` 统一管理 `KnowledgeService` 等单例 | `di_container.py:370-375` |

---

## 4. 当前问题和瓶颈

### 4.1 检索精度不足
- **纯 LIKE 匹配**：无 TF-IDF 或 BM25 相关性评分，结果排序无意义
- **无语义匹配**：用户问 "怎么退钱" 无法匹配到标题为 "退款流程" 的知识条目
- **分词粗糙**：jieba 分词后直接 OR 拼接，大量无关结果

### 4.2 无重排（Rerank）阶段
- 召回结果直接截断后喂给 LLM，若结果数多则重要信息可能被截断丢弃
- 无法保证最相关的知识出现在上下文窗口的前部

### 4.3 知识库能力受限
- 不支持 PDF/网页/富文本文档导入
- 无分块策略（chunking），长文本只能存单字段
- 产品知识的 `extracted_content` 是 JSON 文本而非可独立查询的结构化字段

### 4.4 扩展性局限
- `get_vector_db_path()` 预留接口虽在，但无实际向量化实现
- SQLite 单文件架构不适合高并发检索场景
- 无知识版本管理、未做 A/B 测试或检索效果评估

### 4.5 客服知识管理原始
- 标签为逗号分隔字符串，无法做复杂标签筛选（如多标签 AND 组合查询）
- 批量导入依赖固定 Excel 模板，容错性差

---

## 5. 改进建议

### 5.1 短期（低成本，可快速落地）
1. **引入 BM25 排序**：在 jieba 分词后对 LIKE 结果做 BM25 相关性评分，按分排序
2. **查询改写**：在检索前用 LLM 对用户问题进行改写/扩展，提升关键词匹配率
3. **客服知识标签规范化**：将 `tags` 字段改为关联表，支持多标签组合查询
4. **添加检索结果去重**：基于内容哈希去重，减少 LLM 输入冗余

### 5.2 中期（架构升级）
5. **升级为向量+关键词混合检索**：
   - 引入嵌入模型（如 `text-embedding-3-small` 或火山引擎嵌入 API）
   - 使用 Chroma / Milvus Lite / LanceDB 作为本地向量数据库
   - 混合检索策略：向量相似度 + BM25 关键词加权融合
6. **增加文档摄入能力**：
   - 支持 PDF/Word/网页导入
   - 实现递归文本分割器（RecursiveCharacterTextSplitter）进行智能分块
7. **添加重排（Rerank）阶段**：用 Cross-Encoder 模型对召回结果精排，选取 Top-K 输入 LLM

### 5.3 长期（持续优化）
8. **检索效果评估体系**：构建测试查询集，定期评估 Recall@K / MRR 等指标
9. **知识质量闭环**：收集用户反馈（有用/无用），用于优化检索策略和知识内容
10. **多模态知识**：支持商品视频、图片素材的知识提取与索引
