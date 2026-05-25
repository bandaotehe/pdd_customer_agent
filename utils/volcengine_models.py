"""
火山引擎（Volcengine）API 模型定义
================================

根据火山引擎文档定义的消息输入和输出数据模型，
用于类型检查和数据验证。
"""
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field


# ==============================================================================
# 枚举类型
# ==============================================================================

class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(str, Enum):
    """内容类型"""
    TEXT = "text"
    IMAGE_URL = "image_url"
    VIDEO_URL = "video_url"


class ThinkingType(str, Enum):
    """思考模式"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    AUTO = "auto"


class ResponseFormatType(str, Enum):
    """响应格式类型"""
    TEXT = "text"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class ServiceTier(str, Enum):
    """服务等级"""
    SCALE = "scale"
    DEFAULT = "default"


class FinishReason(str, Enum):
    """结束原因"""
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"


class ToolType(str, Enum):
    """工具类型"""
    FUNCTION = "function"


# ==============================================================================
# 消息内容模型（多模态）
# ==============================================================================

class TextContentPart(BaseModel):
    """文本内容部分"""
    type: str = Field(default="text", description="内容类型，固定为 'text'")
    text: str = Field(..., description="文本内容")


class ImageURL(BaseModel):
    """图片URL"""
    url: str = Field(..., description="图片链接或Base64编码")
    detail: Optional[str] = Field(None, description="理解精细度：low、high、xhigh")
    image_pixel_limit: Optional[Dict[str, int]] = Field(None, description="像素限制")


class ImageContentPart(BaseModel):
    """图片内容部分"""
    type: str = Field(default="image_url", description="内容类型，固定为 'image_url'")
    image_url: ImageURL = Field(..., description="图片内容")


class VideoURL(BaseModel):
    """视频URL"""
    url: str = Field(..., description="视频链接或Base64编码")
    fps: Optional[float] = Field(default=1.0, description="抽帧频率，范围[0.2, 5]")


class VideoContentPart(BaseModel):
    """视频内容部分"""
    type: str = Field(default="video_url", description="内容类型，固定为 'video_url'")
    video_url: VideoURL = Field(..., description="视频内容")


ContentPart = Union[TextContentPart, ImageContentPart, VideoContentPart]


# ==============================================================================
# 工具调用模型
# ==============================================================================

class FunctionCall(BaseModel):
    """函数调用"""
    name: str = Field(..., description="函数名称")
    arguments: str = Field(..., description="函数参数，JSON格式")


class ToolCall(BaseModel):
    """工具调用"""
    id: str = Field(..., description="工具调用ID")
    type: str = Field(default="function", description="工具类型，当前仅支持 'function'")
    function: FunctionCall = Field(..., description="函数调用信息")


class ToolFunctionDefinition(BaseModel):
    """工具函数定义"""
    name: str = Field(..., description="函数名称")
    description: Optional[str] = Field(None, description="函数描述")
    parameters: Optional[Dict[str, Any]] = Field(None, description="函数参数，JSON Schema格式")


class ToolDefinition(BaseModel):
    """工具定义"""
    type: str = Field(default="function", description="工具类型，固定为 'function'")
    function: ToolFunctionDefinition = Field(..., description="函数定义")


class ToolChoiceFunction(BaseModel):
    """工具选择-指定函数"""
    name: str = Field(..., description="函数名称")


class ToolChoiceObject(BaseModel):
    """工具选择对象"""
    type: str = Field(default="function", description="类型，固定为 'function'")
    function: ToolChoiceFunction = Field(..., description="函数信息")


ToolChoice = Union[str, ToolChoiceObject]


# ==============================================================================
# 响应格式模型
# ==============================================================================

class ResponseFormatText(BaseModel):
    """文本响应格式"""
    type: str = Field(default="text", description="类型，固定为 'text'")


class ResponseFormatJsonObject(BaseModel):
    """JSON对象响应格式"""
    type: str = Field(default="json_object", description="类型，固定为 'json_object'")


class JsonSchema(BaseModel):
    """JSON Schema定义"""
    name: str = Field(..., description="JSON结构名称")
    description: Optional[str] = Field(None, description="回复用途描述")
    schema: Dict[str, Any] = Field(..., description="JSON Schema定义")
    strict: Optional[bool] = Field(default=False, description="是否严格遵循模式")


class ResponseFormatJsonSchema(BaseModel):
    """JSON Schema响应格式"""
    type: str = Field(default="json_schema", description="类型，固定为 'json_schema'")
    json_schema: JsonSchema = Field(..., description="JSON Schema定义")


ResponseFormat = Union[ResponseFormatText, ResponseFormatJsonObject, ResponseFormatJsonSchema]


# ==============================================================================
# 思考模式模型
# ==============================================================================

class ThinkingConfig(BaseModel):
    """思考配置"""
    type: ThinkingType = Field(..., description="思考模式：enabled、disabled、auto")


# ==============================================================================
# 流式选项模型
# ==============================================================================

class StreamOptions(BaseModel):
    """流式选项"""
    include_usage: Optional[bool] = Field(default=False, description="是否输出token用量")
    chunk_include_usage: Optional[bool] = Field(default=False, description="每个chunk是否输出累计token用量")


# ==============================================================================
# 输入消息模型
# ==============================================================================

class SystemMessage(BaseModel):
    """系统消息"""
    role: str = Field(default="system", description="角色，固定为 'system'")
    content: Union[str, List[ContentPart]] = Field(..., description="系统消息内容")


class UserMessage(BaseModel):
    """用户消息"""
    role: str = Field(default="user", description="角色，固定为 'user'")
    content: Union[str, List[ContentPart]] = Field(..., description="用户消息内容")


class AssistantMessage(BaseModel):
    """助手消息"""
    role: str = Field(default="assistant", description="角色，固定为 'assistant'")
    content: Optional[Union[str, List[Any]]] = Field(None, description="助手消息内容")
    reasoning_content: Optional[str] = Field(None, description="思维链内容")
    tool_calls: Optional[List[ToolCall]] = Field(None, description="工具调用")


class ToolMessage(BaseModel):
    """工具消息"""
    role: str = Field(default="tool", description="角色，固定为 'tool'")
    content: Union[str, List[Any]] = Field(..., description="工具返回消息")
    tool_call_id: str = Field(..., description="工具调用ID")


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


# ==============================================================================
# Chat Completions 请求模型
# ==============================================================================

class ChatCompletionsRequest(BaseModel):
    """
    火山引擎 Chat Completions 请求模型

    对应文档：POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
    """
    model: str = Field(..., description="调用的模型ID")
    messages: List[Dict[str, Any]] = Field(..., description="消息列表")

    # 可选参数
    thinking: Optional[ThinkingConfig] = Field(default=None, description="思考模式配置")
    stream: Optional[bool] = Field(default=False, description="是否流式返回")
    stream_options: Optional[StreamOptions] = Field(default=None, description="流式选项")
    max_tokens: Optional[int] = Field(default=4096, description="模型回答最大长度")
    max_completion_tokens: Optional[int] = Field(default=None, description="最大输出长度（含思维链）")
    service_tier: Optional[str] = Field(default="auto", description="服务等级：auto、default")
    stop: Optional[Union[str, List[str]]] = Field(default=None, description="停止词")
    reasoning_effort: Optional[str] = Field(default="medium", description="思考工作量：minimal、low、medium、high")
    response_format: Optional[ResponseFormat] = Field(default=None, description="响应格式")
    frequency_penalty: Optional[float] = Field(default=0.0, description="频率惩罚系数，范围[-2.0, 2.0]")
    presence_penalty: Optional[float] = Field(default=0.0, description="存在惩罚系数，范围[-2.0, 2.0]")
    temperature: Optional[float] = Field(default=1.0, description="采样温度，范围[0, 2]")
    top_p: Optional[float] = Field(default=0.7, description="核采样概率阈值，范围[0, 1]")
    logprobs: Optional[bool] = Field(default=False, description="是否返回对数概率")
    top_logprobs: Optional[int] = Field(default=None, description="最可能的token数量")
    logit_bias: Optional[Dict[str, float]] = Field(default=None, description="调整token出现概率")
    tools: Optional[List[ToolDefinition]] = Field(default=None, description="待调用工具列表")
    parallel_tool_calls: Optional[bool] = Field(default=True, description="是否允许并行调用多个工具")
    tool_choice: Optional[ToolChoice] = Field(default=None, description="工具选择：none、required、auto或指定工具")


# ==============================================================================
# 响应模型（非流式）
# ==============================================================================

class LogProbsContent(BaseModel):
    """对数概率内容"""
    token: str = Field(..., description="当前token")
    bytes: Optional[List[int]] = Field(default=None, description="UTF-8值")
    logprob: float = Field(..., description="对数概率")
    top_logprobs: Optional[List[Dict[str, Any]]] = Field(default=None, description="最可能的token列表")


class LogProbs(BaseModel):
    """对数概率"""
    content: Optional[List[LogProbsContent]] = Field(default=None, description="内容对数概率信息")


class ChoiceMessage(BaseModel):
    """选择消息"""
    role: str = Field(..., description="角色，固定为 'assistant'")
    content: Optional[str] = Field(default=None, description="生成的消息内容")
    reasoning_content: Optional[str] = Field(default=None, description="思维链内容")
    tool_calls: Optional[List[ToolCall]] = Field(default=None, description="工具调用")


class Choice(BaseModel):
    """选择"""
    index: int = Field(..., description="在choices列表中的索引")
    finish_reason: FinishReason = Field(..., description="停止生成的原因")
    message: ChoiceMessage = Field(..., description="模型输出内容")
    logprobs: Optional[LogProbs] = Field(default=None, description="对数概率信息")
    moderation_hit_type: Optional[str] = Field(default=None, description="风险分类标签")


class UsageDetails(BaseModel):
    """用量详情"""
    cached_tokens: Optional[int] = Field(default=0, description="缓存token用量")
    reasoning_tokens: Optional[int] = Field(default=0, description="思维链token数")


class Usage(BaseModel):
    """Token用量"""
    total_tokens: int = Field(..., description="总token数量")
    prompt_tokens: int = Field(..., description="输入token数量")
    prompt_tokens_details: Optional[UsageDetails] = Field(default=None, description="输入详情")
    completion_tokens: int = Field(..., description="输出token数量")
    completion_tokens_details: Optional[UsageDetails] = Field(default=None, description="输出详情")


class ChatCompletionsResponse(BaseModel):
    """
    火山引擎 Chat Completions 非流式响应模型
    """
    id: str = Field(..., description="请求唯一标识")
    model: str = Field(..., description="实际使用的模型名称和版本")
    service_tier: Optional[ServiceTier] = Field(default=None, description="服务等级")
    created: int = Field(..., description="创建时间Unix时间戳")
    object: str = Field(default="chat.completion", description="固定为 'chat.completion'")
    choices: List[Choice] = Field(..., description="模型输出内容")
    usage: Usage = Field(..., description="Token用量")


# ==============================================================================
# 响应模型（流式）
# ==============================================================================

class DeltaMessage(BaseModel):
    """增量消息"""
    role: Optional[str] = Field(default=None, description="角色")
    content: Optional[str] = Field(default=None, description="增量内容")
    reasoning_content: Optional[str] = Field(default=None, description="思维链内容")
    tool_calls: Optional[List[ToolCall]] = Field(default=None, description="工具调用")


class StreamChoice(BaseModel):
    """流式选择"""
    index: int = Field(..., description="索引")
    finish_reason: Optional[FinishReason] = Field(default=None, description="停止原因")
    delta: DeltaMessage = Field(..., description="增量内容")
    logprobs: Optional[LogProbs] = Field(default=None, description="对数概率")
    moderation_hit_type: Optional[str] = Field(default=None, description="风险分类标签")


class ChatCompletionsChunkResponse(BaseModel):
    """
    火山引擎 Chat Completions 流式响应模型
    """
    id: str = Field(..., description="请求唯一标识")
    model: str = Field(..., description="实际使用的模型名称和版本")
    service_tier: Optional[ServiceTier] = Field(default=None, description="服务等级")
    created: int = Field(..., description="创建时间Unix时间戳")
    object: str = Field(default="chat.completion.chunk", description="固定为 'chat.completion.chunk'")
    choices: List[StreamChoice] = Field(..., description="模型输出内容")
    usage: Optional[Usage] = Field(default=None, description="Token用量（流式时默认null）")
