"""
LLM 客户端模块

封装与 LLM API 的交互，提供类型安全的请求和响应处理。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("openai package is required: pip install openai>=1.109.1")

from utils.logger_loguru import get_logger
from utils.volcengine_models import ChatCompletionsRequest

logger = get_logger("LLMClient")


@dataclass
class LLMResponse:
    """LLM 响应封装"""
    content: Optional[str]
    tool_calls: Optional[List[Any]]
    reasoning_content: Optional[str] = None
    raw_response: Any = None

    @property
    def has_tool_calls(self) -> bool:
        """是否有工具调用"""
        return self.tool_calls is not None and len(self.tool_calls) > 0


class LLMClient:
    """LLM 客户端封装"""

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model_name: str,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        初始化 LLM 客户端

        Args:
            api_key: API 密钥
            api_base: API 基础地址
            model_name: 模型名称
            temperature: 温度参数
            tools: 可用工具列表
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name
        self.temperature = temperature
        self.tools = tools or []

        self._client: Optional[AsyncOpenAI] = None

    async def initialize(self) -> None:
        """初始化 OpenAI 客户端"""
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base or None,
            timeout=60.0,
        )
        logger.debug(f"LLM 客户端初始化成功: model={self.model_name}")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        发送聊天请求到 LLM

        Args:
            messages: 消息列表
            tool_choice: 工具选择策略

        Returns:
            LLMResponse 封装的响应
        """
        if not self._client:
            raise RuntimeError("LLM 客户端未初始化，请先调用 initialize()")

        # 1. 构建请求参数字典
        request_dict: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        if self.tools:
            request_dict["tools"] = self.tools
            request_dict["tool_choice"] = tool_choice

        # 2. 使用 Pydantic 模型验证请求参数
        try:
            validated_request = ChatCompletionsRequest(**request_dict)
            logger.debug("请求参数验证通过")
        except Exception as e:
            logger.error(f"请求参数验证失败: {e}")
            raise

        # 3. 调试日志：输出发送给 LLM 的最后一条消息格式
        if messages:
            last_msg = messages[-1]
            content = last_msg.get("content", "")
            if isinstance(content, list):
                logger.info(f"[LLM] 多模态消息 content_parts={len(content)}: "
                           f"{[c.get('type','?') for c in content]}")
                for part in content:
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        logger.info(f"[LLM] image_url: {url[:80]}... (len={len(url)})")
            else:
                logger.debug(f"发送给 LLM 的消息数: {len(messages)}, 最后一条长度={len(str(content))}")

        # 4. 调用 API
        response = await self._client.chat.completions.create(
            **validated_request.model_dump(exclude_none=True)
        )
        message = response.choices[0].message

        # 5. 记录 token 使用情况
        if response.usage:
            logger.debug(f"使用了 {response.usage.total_tokens} tokens "
                        f"(prompt: {response.usage.prompt_tokens}, "
                        f"completion: {response.usage.completion_tokens})")

        # 6. 调试日志：输出 LLM 的响应
        if message.tool_calls:
            tool_names = [tc.function.name for tc in message.tool_calls]
            logger.info(f"LLM 决定调用工具: {tool_names}")
        else:
            logger.debug(f"LLM 直接回复: {str(message.content)[:200]}...")

        return LLMResponse(
            content=message.content,
            tool_calls=message.tool_calls,
            reasoning_content=getattr(message, "reasoning_content", None),
            raw_response=response,
        )
