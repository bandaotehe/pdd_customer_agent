# 拼多多商家后台消息获取技术详解

## 1. 核心技术：WebSocket 实时推送（非爬虫）

本项目的消息获取**不是通过 HTML 爬虫或 DOM 解析**实现的，而是直接复用了拼多多商家后台 Web 端的 **WebSocket 通信协议**。核心原理：

> 拼多多商家后台 (`mms.pinduoduo.com`) 的前端页面通过 WebSocket 与服务器保持长连接，实时接收客户消息。本项目模拟了这一过程——用 `websockets` 库建立同样的 WebSocket 连接，以商家身份接收完全相同的实时消息流。

### 技术对比

| 技术手段 | 本项目的方案 | 传统爬虫 |
|----------|-------------|---------|
| **连接方式** | WebSocket 长连接 (wss://) | HTTP 轮询 |
| **数据获取** | 服务器主动推送 | 解析 HTML DOM |
| **实时性** | 毫秒级 | 秒级~分钟级 |
| **认证方式** | access_token + cookies | cookies |
| **反爬风险** | 低（模拟正常前端行为） | 中高 |
| **消息覆盖** | 仅 WebSocket 连接期间 | 取决于页面能加载多少 |

---

## 2. 完整技术链路（分步拆解）

### 2.1 第一步：账号登录 → 获取 Cookies

**技术手段：Playwright 浏览器自动化**（非 requests 模拟请求）

```
用户点击"添加账号" → Playwright 启动 Chromium → 打开 mms.pinduoduo.com → 输入用户名密码 → 处理验证码 → 登录成功后提取 cookies
```

**为什么要用 Playwright 而不是 requests？**
拼多多商家后台的登录有验证码、反自动化检测、复杂的 JS 执行流程，用纯 requests 无法绕过。必须用真实浏览器环境。

**对应代码** (`scripts/install_playwright.py` + `Channel/pinduoduo/pdd_login.py`):

```python
# pdd_login.py - 核心登录逻辑（简化）
from playwright.async_api import async_playwright

async def login_pdd(channel_name, name, password):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 有头模式，方便处理验证码
        page = await browser.new_page()
        await page.goto("https://mms.pinduoduo.com/login")
        # 填写登录表单
        await page.fill("input[placeholder*='账号']", name)
        await page.fill("input[placeholder*='密码']", password)
        # 用户手动处理验证码后点击登录
        # ...
        # 登录成功后提取 cookies
        cookies = await page.context.cookies()
        await browser.close()
        return cookies
```

**Cookies 存储**：登录成功后，cookies JSON 写入 `accounts` 表：

```python
db_manager.add_account(
    channel_name="pinduoduo",
    shop_id="721468769",
    user_id="184397855",
    username="店铺客服账号",
    cookies=json.dumps(cookies_list),  # cookies 序列化存储
)
```

### 2.2 第二步：获取 WebSocket 令牌 (access_token)

**技术手段：HTTP POST + Cookies 鉴权**

有了 cookies 后，调用拼多多 `getToken` API 获取 WebSocket 连接所需的临时令牌。

**对应代码** (`Channel/pinduoduo/utils/API/get_token.py`):

```python
# get_token.py
from ..base_request import BaseRequest

class GetToken(BaseRequest):        # 继承 BaseRequest，自动带 cookies
    def get_token(self) -> str | None:
        url = "https://mms.pinduoduo.com/chats/getToken"
        data = {"version": "3"}
        result = self.post(url, json_data=data)
        if result:
            if "token" in result:
                return result["token"]
            elif "result" in result and "token" in result["result"]:
                return result["result"]["token"]
        return None
```

**BaseRequest 如何携带 cookies** (`Channel/pinduoduo/utils/base_request.py`):

```python
# base_request.py（关键部分）
class BaseRequest:
    def __init__(self, shop_id, user_id):
        # 从数据库加载 cookies
        account_info = db_manager.get_account("pinduoduo", shop_id, user_id)
        cookies_data = account_info.get('cookies')
        self.cookies = json.loads(cookies_data)  # 反序列化 cookies

    def post(self, url, json_data=None, headers=None):
        """发送 POST 请求，自动携带 cookies"""
        merged_headers = {**self.default_headers, **(headers or {})}
        response = requests.post(
            url,
            json=json_data,
            headers=merged_headers,
            cookies=self.cookies,       # ← 关键：带上商家 cookies
            timeout=30
        )
        return self._execute_with_retry(response)  # 含重试 + 过期检测
```

**Cookie 过期自动刷新机制**：

```python
# base_request.py — 会话过期自动重登录
SESSION_EXPIRED_ERROR_CODE = 43001

def _is_session_expired(self, response_data):
    error_code = response_data.get("result", {}).get("error_code")
    error_msg = response_data.get("result", {}).get("error", "")
    return error_code == 43001 and "会话已过期" in error_msg

def _relogin_and_update_cookies(self):
    # 第一步：尝试无交互刷新 cookies
    result = pdd_login.refresh_pdd_cookies(username, password)
    if result:
        self.cookies = result
        db_manager.update_account_cookies(...)  # 持久化
        return True
    # 第二步：回退到完整 Playwright 登录
    result = pdd_login.login_pdd(username, password)
    if result:
        self.cookies = result
        db_manager.update_account_cookies(...)
        return True
    return False
```

### 2.3 第三步：建立 WebSocket 长连接

**技术手段：Python `websockets` 库 + asyncio**

拿到 `access_token` 后，建立 `wss://` WebSocket 连接。这是消息获取的**核心技术**。

**对应代码** (`Channel/pinduoduo/core/pdd_lifecycle.py`):

```python
# pdd_lifecycle.py — WebSocket 连接建立（核心代码）
import websockets
from Channel.pinduoduo.utils.API.get_token import GetToken

API_VERSION = "202506091557"  # 拼多多 WebSocket 协议版本号

async def init(self, shop_id, user_id, username):
    # 1. 获取令牌
    token = GetToken(shop_id, user_id)
    access_token = token.get_token()  # HTTP POST → 获取临时 JWT

    # 2. 拼接 WebSocket URL（完全模拟浏览器端的连接参数）
    params = {
        "access_token": access_token,
        "role": "mall_cs",          # 角色：商家客服
        "client": "web",            # 客户端类型：Web
        "version": API_VERSION,     # 协议版本：202506091557
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"wss://m-ws.pinduoduo.com/?{query}"
    # 结果：wss://m-ws.pinduoduo.com/?access_token=xxx&role=mall_cs&client=web&version=202506091557

    # 3. 建立 WebSocket 连接
    async with websockets.connect(
        full_url,
        ping_interval=60,           # 每 60 秒发 ping 保活
        ping_timeout=30,            # ping 超时时间
        max_size=10**7,             # 最大消息 10MB
        compression=None,           # 不使用压缩
        close_timeout=10            # 关闭超时
    ) as websocket:
        # 连接成功！
        self.ws = websocket
        status_manager.set_connected(shop_id, user_id)

        # 4. 进入消息接收循环（异步并发）
        await asyncio.gather(
            self._message_loop(websocket, ...),    # 消息接收
            self._heartbeat_loop(websocket, ...),  # 心跳保持
        )
```

### 2.4 第四步：消息接收循环（核心）

**这就是获取对话信息的关键代码。**

WebSocket 连接建立后，拼多多服务器会**主动推送**每一条客户消息。本项目通过 `async for message in websocket` 逐条接收。

**对应代码** (`Channel/pinduoduo/core/pdd_lifecycle.py`):

```python
# pdd_lifecycle.py — _message_loop()
async def _message_loop(self, websocket, shop_id, user_id, username, queue_name):
    """消息接收主循环 — 这是获取对话数据的核心"""
    try:
        # async for 循环：持续等待服务器推送消息
        async for message in websocket:
            # message 是一条原始的 JSON 字符串

            # 检查是否需要停止
            if self._stop_event.is_set():
                break

            # 为每条消息创建独立的处理任务（并发处理）
            task = asyncio.create_task(
                self._process_websocket_message_concurrent(
                    message, shop_id, user_id, username, queue_name
                )
            )
            self.processing_tasks.add(task)

    except websockets.ConnectionClosed as e:
        # 连接关闭 → 触发重连逻辑
        logger.warning(f"WebSocket 连接关闭: code={e.code}")
```

**并发控制**：用 `asyncio.Semaphore(50)` 限制最多 50 条消息同时处理：

```python
async def _process_websocket_message_concurrent(self, message, ...):
    async with self.message_semaphore:  # 信号量，最多 50 个并发
        await self._process_websocket_message(message, ...)
```

### 2.5 第五步：解析原始 WebSocket 消息

**WebSocket 推送的原始消息是什么样的？**

拼多多服务器推送到 WebSocket 的消息是 JSON 格式，没有加密（保护机制是 access_token 鉴权）。

```json
// 客户发送文本消息 "你好"
{
  "response": "push",
  "message": {
    "type": 0,
    "msg_id": "msg_abc123",
    "from": { "role": "user", "uid": "9876543210" },
    "to": { "role": "mall_cs", "uid": "1234567890" },
    "content": "你好",
    "nickname": "客户张三",
    "time": 1715678900
  }
}

// 客户发送图片
{
  "response": "push",
  "message": {
    "type": 1,
    "msg_id": "msg_def456",
    "from": { "role": "user", "uid": "9876543210" },
    "content": "https://img.pddpic.com/xxx.jpg",
    "nickname": "客户张三"
  }
}

// WebSocket 认证结果
{
  "response": "auth",
  "uid": "1234567890",
  "auth": { "result": "ok" },
  "status": "connected"
}

// 客户撤回消息
{
  "response": "push",
  "message": {
    "type": 1002,
    "info": { "withdraw_hint": "客户撤回了一条消息" }
  }
}

// 客户咨询商品规格
{
  "response": "push",
  "message": {
    "type": 64,
    "info": {
      "data": {
        "goodsID": "12345678",
        "goodsName": "某商品名称",
        "spec": "颜色:白色;尺码:XL"
      }
    }
  }
}
```

**解析代码** (`Channel/pinduoduo/pdd_message.py`):

```python
# pdd_message.py — 消息解析（完整逻辑）
class PDDChatMessage:
    def __init__(self, raw_msg: dict):
        # raw_msg 是 WebSocket 收到的原始 JSON 字典
        self.msg = raw_msg

        # 解析基础字段
        message = raw_msg.get("message", {})
        self.msg_id = message.get("msg_id")
        self.nickname = message.get("nickname")
        self.from_uid = message.get("from", {}).get("uid")   # 谁发的（客户 UID）
        self.to_uid = message.get("to", {}).get("uid")       # 发给谁（商家 UID）

        # 跳过商家自己发出的消息（不处理 echo）
        if message.get("from", {}).get("role") == "mall_cs":
            return

        # 根据 response 字段分派
        response = raw_msg.get("response")
        if response == "push":
            msg_type = message.get("type")  # 消息类型编号
            if msg_type == 0:       # 文本
                sub_type = message.get("sub_type")
                if sub_type == 1:   # 订单咨询
                    self.type = "ORDER_INFO"
                    self.content = {
                        "order_id": message["info"]["orderSequenceNo"],
                        "goods_name": message["info"]["goodsName"],
                    }
                elif sub_type == 0: # 商品咨询
                    self.type = "GOODS_INQUIRY"
                    self.content = {
                        "goods_id": message["info"]["goodsID"],
                        "goods_name": message["info"]["goodsName"],
                        "goods_price": message["info"]["goodsPrice"],
                    }
                else:               # 普通文本
                    self.type = "TEXT"
                    self.content = message.get("content")  # 消息正文
            elif msg_type == 1:     # 图片
                self.type = "IMAGE"
                self.content = message.get("content")      # 图片 URL
            elif msg_type == 5:     # 表情
                self.type = "EMOTION"
            elif msg_type == 14:    # 视频
                self.type = "VIDEO"
            elif msg_type == 64:    # 商品规格咨询
                self.type = "GOODS_SPEC"
            elif msg_type == 1002:  # 撤回
                self.type = "WITHDRAW"
            elif msg_type == 24:    # 转接
                self.type = "TRANSFER"
```

### 2.6 第六步：消息转换为统一 Context

解析后的消息转为标准的 `Context` 对象，方便下游 AI 处理器统一处理。

**代码** (`Channel/pinduoduo/core/pdd_message_handler.py`):

```python
# pdd_message_handler.py — 转换为统一 Context
def _convert_to_context(self, pdd_message, shop_id, user_id, username):
    # 将拼多多特有字段打包为 kwargs
    context = Context.create_pinduoduo_context(
        content=pdd_message.content,          # 消息正文
        msg_id=pdd_message.msg_id,            # 消息 ID
        from_uid=pdd_message.from_uid,        # 客户的拼多多 UID
        to_uid=pdd_message.to_uid,            # 商家的拼多多 UID
        nickname=pdd_message.nickname,        # 客户昵称
        user_msg_type=pdd_message.type,       # 消息类型枚举
        shop_id=shop_id,                      # 店铺 ID
        user_id=user_id,                      # 账号 ID
        username=username,                    # 账号用户名
        shop_name=shop_name,                  # 店铺名称
        raw_data=pdd_message.msg,             # 原始 JSON（保留完整数据）
        channel_type=ChannelType.PINDUODUO,
    )
    return context
```

**Context 数据结构** (`bridge/context.py`):

```python
class PinduoduoKwargs(BaseModel):
    """拼多多消息的完整上下文参数"""
    msg_id: Optional[str] = None          # 消息唯一 ID
    shop_name: Optional[str] = None       # 店铺名称
    from_user: Optional[str] = None       # 发送者角色
    from_uid: Optional[str] = None        # 发送者 UID（客户唯一标识）
    to_user: Optional[str] = None         # 接收者角色
    to_uid: Optional[str] = None          # 接收者 UID
    nickname: Optional[str] = None        # 客户昵称
    timestamp: Optional[str] = None       # 时间戳
    user_msg_type: Optional[str] = None   # 消息类型
    shop_id: Optional[str] = None         # 店铺 ID
    user_id: Optional[str] = None         # 登录账号 ID
    username: Optional[str] = None        # 登录账号用户名
    raw_data: Optional[dict] = None       # 原始 JSON 数据
```

### 2.7 第七步：消息分发与 AI 处理

转换后的 Context 进入路由：

```
消息处理路由：
  │
  ├─ 系统消息 (AUTH / SYSTEM_STATUS / MALL_CS)
  │     → 直接处理（记录日志）
  │
  ├─ 撤回消息 (WITHDRAW) / 转接 (TRANSFER)
  │     → 发送"[玫瑰]"回复
  │
  └─ 客户消息 (TEXT / IMAGE / VIDEO / EMOTION / GOODS_INQUIRY / ORDER_INFO)
        → 进入异步队列 (put_message)
        → MessageConsumer 消费
        → Handler Chain:
            ├─ KeywordDetectionHandler  → 检测关键词 → 命中则直接回复
            ├─ AIReplyHandler           → 调用 CustomerAgent → LLM 生成回复
            └─ CatchAllHandler          → 兜底回复
```

**代码** (`Channel/pinduoduo/core/pdd_message_handler.py`):

```python
# 消息路由逻辑
async def _process_websocket_message(self, message, shop_id, user_id, username, queue_name):
    # 1. JSON 解析
    message_data = json.loads(message)

    # 2. 创建 PDDChatMessage（自动识别类型）
    pdd_message = PDDChatMessage(message_data)

    # 3. 转换为 Context
    context = self._convert_to_context(pdd_message, shop_id, user_id, username)

    # 4. 路由分发
    if self._should_process_immediately(context):
        # 系统消息 → 立即处理
        await self._handle_immediate_message(context, shop_id, user_id)
    elif self._should_queue_message(context):
        # 客户消息 → 入队等待 AI 处理
        await put_message(queue_name, context)
    else:
        # 不支持的类型 → 忽略
        pass
```

### 2.8 第八步：发送回复

**技术手段：HTTP POST + cookies 鉴权**

回复不是通过 WebSocket 发出的，而是通过 HTTP POST 调用拼多多的 `send_message` API。

**代码** (`Channel/pinduoduo/utils/API/send_message.py`):

```python
class SendMessage(BaseRequest):
    def send_text(self, recipient_uid, message_content):
        """发送文本消息给指定客户"""
        url = "https://mms.pinduoduo.com/plateau/chat/send_message"
        data = {
            "data": {
                "cmd": "send_message",
                "request_id": int(time.time() * 1000),
                "message": {
                    "to": {"role": "user", "uid": recipient_uid},  # 目标客户 UID
                    "from": {"role": "mall_cs"},                    # 发送者：商家客服
                    "content": message_content,                     # 消息内容
                    "type": 0,                                      # 0=文本, 1=图片
                    "is_aut": 0,                                    # 非自动回复
                    "manual_reply": 1,                              # 手动回复标记
                },
            },
            "client": "WEB"
        }
        result = self.post(url, json_data=data)  # 继承 BaseRequest，自动带 cookies
        return result
```

---

## 3. 完整数据流总览

```
┌─────────────────────────────────────────────────────────────────┐
│ 拼多多服务器                                                        │
│                                                                     │
│  ① 客户在拼多多 App 发消息 "你好，这个商品多少钱"                         │
│     │                                                               │
│     ▼                                                               │
│  ② 服务器通过 WebSocket 推送给商家后台                                  │
│     │  原始 JSON: {"response":"push","message":{"type":0,...}}       │
│     │                                                               │
└─────┬───────────────────────────────────────────────────────────────┘
      │
      │  wss://m-ws.pinduoduo.com/?access_token=xxx&role=mall_cs
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 本项目 (Customer-Agent)                                             │
│                                                                     │
│  ③ _message_loop(): async for message in websocket:                 │
│     │                                                               │
│     ▼ 原始 JSON 字符串 "{\"response\":\"push\",...}"                   │
│  ④ PDDChatMessage(msg): 解析类型、提取字段                            │
│     │  from_uid="9876543210", content="你好，这个商品多少钱"             │
│     │                                                               │
│     ▼                                                               │
│  ⑤ Context.create_pinduoduo_context(...): 转换为标准 Context          │
│     │  context.type=TEXT, context.kwargs.from_uid="9876543210"       │
│     │                                                               │
│     ▼                                                               │
│  ⑥ put_message(queue_name, context): 放入 asyncio 消息队列             │
│     │                                                               │
│     ▼                                                               │
│  ⑦ Handler Chain 处理                                               │
│     │                                                               │
│     ├─ KeywordDetectionHandler: 检查关键词匹配                        │
│     │   └─ 命中 "价格" → 返回预设回复                                  │
│     │                                                               │
│     └─ AIReplyHandler → CustomerAgent.async_reply(query, context)     │
│         │                                                           │
│         ├─ 构建 session_id = "pinduoduo_721468769_9876543210"        │
│         ├─ 加载历史消息 (agent.db)                                    │
│         ├─ LLM 调用 (带知识库工具调用)                                 │
│         └─ 生成回复: "亲，这个商品目前售价 29.9 元..."                    │
│                                                                     │
│  ⑧ SendMessage.send_text(recipient_uid, reply_text)                 │
│     │  POST https://mms.pinduoduo.com/plateau/chat/send_message      │
│     │  cookies = {...}  (商家登录态)                                   │
│     │                                                               │
└─────┬───────────────────────────────────────────────────────────────┘
      │
      │  HTTP POST + cookies
      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 拼多多服务器                                                        │
│  ⑨ 服务器收到回复，推送给客户的拼多多 App                                │
│     客户在 App 中看到: "亲，这个商品目前售价 29.9 元..."                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 关键技术总结

### 4.1 用到的技术栈

| 技术 | 用途 | 对应 Python 库 |
|------|------|---------------|
| **WebSocket** | 实时接收客户消息 | `websockets` (asyncio) |
| **HTTP POST** | 发送回复、获取 Token、查询商品 | `requests` |
| **Playwright** | 账号登录、获取 cookies | `playwright` |
| **SQLite** | 存储 cookies、会话记录、消息 | `sqlalchemy` |
| **asyncio** | 异步并发消息处理 | 标准库 |
| **Pydantic** | 消息数据结构验证 | `pydantic` |

### 4.2 为什么不是爬虫？

爬虫通常指解析 HTML 页面、模拟点击、提取 DOM 元素。本项目的消息获取**完全不接触 HTML 页面**：

- **消息接收**：直接复用拼多多前端的 WebSocket 协议
- **消息发送**：调用与拼多多前端相同的 HTTP API
- **登录**：Playwright 浏览器自动化获取 cookies（这一步可以说用了浏览器自动化技术，但后续消息处理完全基于协议层，不解析任何 HTML）

### 4.3 局限

1. **仅实时消息**：WebSocket 连接建立后才能收到消息。连接之前的历史消息无法通过当前 API 获取（平台未提供历史消息批量拉取接口）。
2. **单账号单连接**：每个商家账号独立建立一条 WebSocket 连接。
3. **依赖协议版本**：`API_VERSION = "202506091557"` 可能随平台更新而变化，需要跟进维护。

---

## 5. 关键文件索引

| 文件 | 职责 |
|------|------|
| `Channel/pinduoduo/pdd_message.py` | 原始 WebSocket 消息解析（JSON → PDDChatMessage） |
| `Channel/pinduoduo/core/pdd_lifecycle.py` | WebSocket 连接 + 消息接收循环 + 心跳 |
| `Channel/pinduoduo/core/pdd_connection.py` | 连接建立 + 指数退避重连 |
| `Channel/pinduoduo/core/pdd_message_handler.py` | 消息→Context 转换 + 路由分发 |
| `Channel/pinduoduo/utils/API/get_token.py` | 获取 WebSocket access_token |
| `Channel/pinduoduo/utils/API/send_message.py` | 发送文本/图片/商品卡片 + 会话转移 |
| `Channel/pinduoduo/utils/base_request.py` | HTTP API 基类：cookies 管理 + 重试 + 自动重登录 |
| `Channel/pinduoduo/pdd_login.py` | Playwright 浏览器自动化登录 |
| `bridge/context.py` | Context + PinduoduoKwargs 数据模型 |
| `Agent/CustomerAgent/custom/session_manager.py` | 会话消息持久化（agent_messages + sessions） |
