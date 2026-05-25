"""
自定义 CustomerAgent 实现

完全自主实现，不依赖 Agno 框架。

本模块已重构，职责分离为：
- agent_config.py: 配置管理
- llm_client.py: LLM 客户端封装
- message_builder.py: 消息和 Prompt 构建
- tool_executor.py: 工具执行器
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from Agent.bot import Bot

# 导入工具模块，触发 @agent_tool 装饰器注册
from Agent.CustomerAgent.tools import (
    send_goods_link,                  # noqa: F401  — 注册 send_goods_link 工具
    move_conversation,                 # noqa: F401  — 注册 transfer_conversation 工具
    get_product_list,                 # noqa: F401  — 注册 get_shop_products 工具
    get_product_knowledge,             # noqa: F401  — 注册 get_product_knowledge 工具
    search_customer_service_knowledge,  # noqa: F401  — 注册 search_customer_service_knowledge 工具
    send_product_image,               # noqa: F401  — 注册 send_product_image 工具
)
from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from Agent.CustomerAgent.custom.session_manager import SessionManager
from Agent.CustomerAgent.custom.tool_decorator import get_tools_for_llm
from utils.logger_loguru import get_logger

# 导入重构后的模块
from Agent.CustomerAgent.custom.agent_config import (
    AgentConfig,
    DEFAULT_DB_PATH,
    DEFAULT_TOKEN_WINDOW,
    DEFAULT_COMPRESS_RATIO,
    DEFAULT_RETAIN_COUNT,
    DEFAULT_MAX_LOOPS,
    DEFAULT_TEMPERATURE,
)
from Agent.CustomerAgent.custom.llm_client import LLMClient, LLMResponse
from Agent.CustomerAgent.custom.message_builder import MessageBuilder
from Agent.CustomerAgent.custom.media_utils import download_images_as_data_uris
from Agent.CustomerAgent.custom.tool_executor import ToolExecutor, ToolResult

logger = get_logger("CustomerAgent")


class CustomerAgent(Bot):
    """
    自定义客服 Agent

    核心循环：
    1. 加载历史消息
    2. 检查上下文压缩
    3. 构建 messages 列表
    4. 调用 LLM → 解析 tool_calls
    5. 并行执行工具 → 回传结果
    6. 循环直到无工具调用
    7. 返回最终回复

    职责已分离到子模块：
    - AgentConfig: 配置管理
    - LLMClient: LLM API 调用
    - MessageBuilder: 消息和 Prompt 构建
    - ToolExecutor: 工具执行
    - SessionManager: 会话管理（已有独立模块）
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        token_window: int = DEFAULT_TOKEN_WINDOW,
        compress_ratio: float = DEFAULT_COMPRESS_RATIO,
        retain_count: int = DEFAULT_RETAIN_COUNT,
        max_loops: int = DEFAULT_MAX_LOOPS,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        super().__init__()
        self._is_initialized = False

        # 配置参数
        self._config = AgentConfig(
            db_path=db_path or DEFAULT_DB_PATH,
            token_window=token_window,
            compress_ratio=compress_ratio,
            retain_count=retain_count,
            max_loops=max_loops,
            temperature=temperature,
        )

        # 子组件（延迟初始化）
        self._llm_client: Optional[LLMClient] = None
        self._message_builder: Optional[MessageBuilder] = None
        self._tool_executor: Optional[ToolExecutor] = None
        self._session_manager: Optional[SessionManager] = None
        self._tools: List[Dict[str, Any]] = []

        logger.info("CustomerAgent 实例创建成功")

    async def initialize_async(self) -> bool:
        """异步初始化 Agent"""
        if self._is_initialized:
            return True

        try:
            # 1. 从配置文件加载配置
            self._config = AgentConfig.load_from_config()

            # 2. 验证配置
            if not self._config.validate():
                return False

            # 3. 初始化 LLM 客户端
            self._llm_client = LLMClient(
                api_key=self._config.api_key,
                api_base=self._config.api_base,
                model_name=self._config.model_name,
                temperature=self._config.temperature,
            )
            await self._llm_client.initialize()

            # 4. 初始化会话管理器
            self._session_manager = SessionManager(
                db_path=self._config.db_path,
                token_window=self._config.token_window,
                compress_ratio=self._config.compress_ratio,
                retain_count=self._config.retain_count,
                model_name=self._config.model_name,
            )

            # 5. 初始化消息构建器
            self._message_builder = MessageBuilder(
                instructions=self._config.instructions,
            )

            # 6. 初始化工具执行器
            self._tool_executor = ToolExecutor()

            # 7. 加载工具列表
            self._tools = get_tools_for_llm()
            self._llm_client.tools = self._tools
            tool_names = [t.get("function", {}).get("name", "unknown") for t in self._tools]
            logger.info(f"已加载 {len(self._tools)} 个工具: {tool_names}")

            self._is_initialized = True
            logger.info(f"CustomerAgent 初始化成功: model={self._config.model_name}")
            return True

        except Exception as e:
            logger.error(f"CustomerAgent 初始化失败: {e}")
            return False

    async def async_reply(self, query: str, context: Context = None) -> Reply:
        """异步回复接口"""
        # 延迟初始化
        if not self._is_initialized:
            if not await self.initialize_async():
                return Reply(ReplyType.ERROR, "AI客服初始化失败，请检查配置。")

        try:
            # 构建 session_id 和 dependencies
            # 注意：kwargs.user_id 是店铺账号 ID，kwargs.from_uid 才是客户唯一标识
            shop_id = ""
            channel_type = ""
            customer_id = ""
            if context and context.channel_type and hasattr(context.kwargs, "from_uid"):
                channel_type = context.channel_type.value
                customer_id = str(context.kwargs.from_uid or "")
                shop_id = str(context.kwargs.shop_id or "")
                session_id = f"{channel_type}_{shop_id}_{customer_id}"
                dependencies = self._message_builder.build_dependencies(context)
            else:
                # 降级：使用 query hash 作为 session_id
                session_id = f"fallback_{abs(hash(query)) % 100000}"
                dependencies = {}

            # 图片/视频消息：检查视觉能力
            if context and context.type in (ContextType.IMAGE, ContextType.VIDEO):
                from config import config as _cfg
                if not _cfg.get("llm.supports_vision", False):
                    # 纯文本模型 → 标记需要转人工
                    media_type = "图片" if context.type == ContextType.IMAGE else "视频"
                    return Reply(ReplyType.TEXT,
                                 f"您的{media_type}已收到，正在为您转接人工客服处理，请稍候。"
                                 f"\n[TRANSFER_NEEDED]")

                # 视觉模型 → 下载图片并转为 data URI
                media_urls = getattr(context, "media_urls", []) or []
                if media_urls:
                    logger.info(f"下载 {len(media_urls)} 张图片用于视觉识别")
                    data_uris = await download_images_as_data_uris(media_urls)
                    if data_uris:
                        dependencies["media_data_uris"] = data_uris
                        if context.type == ContextType.IMAGE:
                            query = query or (
                                "客户发送了一张图片。请描述图片内容，结合上下文判断客户意图。"
                                "如果图片是商品，帮客户查找相似商品并推荐。"
                            )
                        else:
                            query = query or "用户发送了一段视频的截图，请根据图片内容回复用户的问题"
                    else:
                        logger.warning("图片下载失败，回退为纯文本")
                else:
                    logger.warning("收到图片/视频消息但无 media_urls")

            # 加载历史并检查压缩
            history = self._session_manager.get_history(session_id)
            if self._session_manager.should_compress(session_id):
                logger.info(f"触发上下文压缩: session_id={session_id}")
                await self._compress_with_llm(session_id, history, shop_id=shop_id)

            # 保存用户消息到历史
            self._session_manager.add_message(
                session_id=session_id,
                role="user",
                content=query,
                shop_id=shop_id,
                channel_type=channel_type,
                user_id=customer_id,
            )

            # 构建 messages
            messages = self._message_builder.build_messages(query, history, dependencies)

            # 执行 Agent 循环
            final_content = await self._run_agent_loop(messages, dependencies)

            # 保存最终回复到历史
            self._session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=final_content,
                shop_id=shop_id,
                channel_type=channel_type,
                user_id=customer_id,
            )

            return Reply(ReplyType.TEXT, final_content or "抱歉，我暂时无法回复。")

        except Exception as e:
            logger.error(f"CustomerAgent 回复失败: {e}")
            return Reply(ReplyType.ERROR, f"Agent 异常: {e}")

    async def _run_agent_loop(
        self,
        messages: List[Dict[str, Any]],
        dependencies: Dict[str, Any],
    ) -> str:
        """
        Agent 循环核心

        调用 LLM → 检查 tool_calls → 并行执行工具 → 回传结果 → 循环
        """
        loop_count = 0

        while loop_count < self._config.max_loops:
            # 1. 调用 LLM
            try:
                response = await self._llm_client.chat(messages, tool_choice="auto")
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                if loop_count > 0:
                    # 已有中间结果，返回已生成的内容
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant" and msg.get("content"):
                            return msg["content"]
                # 首轮失败或没有中间结果，抛出异常让外层处理
                raise RuntimeError(f"LLM 调用失败: {e}") from e

            # 2. 解析响应
            if not response.has_tool_calls:
                # 无工具调用，返回内容
                content = response.content or ""
                assistant_msg = {"role": "assistant", "content": content}
                if response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                messages.append(assistant_msg)
                return content

            # 3. 保存 assistant 消息（包含 tool_calls）
            assistant_msg = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "type": "function",
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            messages.append(assistant_msg)

            # 4. 检查循环上限
            if loop_count >= self._config.max_loops - 1:
                logger.warning(f"工具调用达到上限 {self._config.max_loops}，强制结束循环")
                messages.append({
                    "role": "user",
                    "content": "[已达到最大工具调用次数，请基于已有信息给出最终回复。]",
                })
                try:
                    final_response = await self._llm_client.chat(messages)
                    return final_response.content or assistant_msg["content"]
                except Exception:
                    return assistant_msg["content"]

            # 5. 并行执行所有工具调用
            tool_results = await self._tool_executor.execute_parallel(
                response.tool_calls, dependencies
            )

            # 6. 将结果追加到消息列表
            for result in tool_results:
                messages.append(result.to_dict())

            loop_count += 1

        # 兜底
        return messages[-1].get("content", "")

    async def _compress_with_llm(
        self,
        session_id: str,
        history: List[Dict[str, Any]],
        shop_id: str = "",
    ) -> None:
        """使用 LLM 生成摘要并压缩历史"""

        def summary_llm(messages: List[Dict[str, Any]]) -> str:
            """同步调用 LLM 生成摘要"""
            summary_prompt = (
                "请简洁地总结以下对话的要点，保留关键信息和用户意图。\n\n"
                f"对话内容（共 {len(messages)} 条消息）：\n"
                + "\n".join(
                    f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')[:200]}"
                    for msg in messages
                    if msg.get("content")
                )
            )

            # 在线程中使用 asyncio.run 创建新的事件循环执行协程
            try:
                response = asyncio.run(
                    self._llm_client.chat(
                        messages=[
                            {"role": "system", "content": "你是一个对话摘要助手。请简洁地总结对话要点。"},
                            {"role": "user", "content": summary_prompt},
                        ],
                        tool_choice="none",
                    )
                )
                return response.content or "[摘要生成失败]"
            except RuntimeError:
                # 如果当前已有事件循环（某些环境中），降级为同步返回
                return "[对话历史摘要]"
            except Exception:
                return "[摘要生成失败]"

        self._session_manager.compress_history(session_id, summary_llm, shop_id=shop_id)
