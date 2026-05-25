"""
Agent 配置模块

管理 Agent 的默认配置和运行时配置参数。
"""
from typing import List, Optional
from dataclasses import dataclass, field

from config import get_config
from utils.logger_loguru import get_logger

logger = get_logger("AgentConfig")

# 默认参数
DEFAULT_DB_PATH = "./temp/agent.db"
# Token 窗口大小：128k context，用于控制上下文长度
DEFAULT_TOKEN_WINDOW = 131072
# 压缩阈值比例：当历史消息超过 token_window * compress_ratio 时触发压缩
DEFAULT_COMPRESS_RATIO = 0.7
# 压缩时保留的最近消息条数
DEFAULT_RETAIN_COUNT = 10
# Agent 循环最大次数（防止无限工具调用）
DEFAULT_MAX_LOOPS = 5
# LLM 温度参数：0.0-2.0，值越高越随机，值越低越确定
DEFAULT_TEMPERATURE = 0.3


@dataclass
class AgentConfig:
    """Agent 配置数据类"""
    db_path: str = field(default_factory=lambda: get_config("db_path", DEFAULT_DB_PATH))
    token_window: int = DEFAULT_TOKEN_WINDOW
    compress_ratio: float = DEFAULT_COMPRESS_RATIO
    retain_count: int = DEFAULT_RETAIN_COUNT
    max_loops: int = DEFAULT_MAX_LOOPS
    temperature: float = DEFAULT_TEMPERATURE

    # LLM 配置
    model_name: str = field(default_factory=lambda: get_config("llm.model_name", "gpt-3.5-turbo"))
    api_key: str = field(default_factory=lambda: get_config("llm.api_key", ""))
    api_base: str = field(default_factory=lambda: get_config("llm.api_base", ""))

    # Prompt 配置（仅 instructions 可配置，description 和 additional_context 由代码硬编码）
    instructions: List[str] = field(default_factory=lambda: get_config("prompt.instructions", []))

    @classmethod
    def load_from_config(cls) -> "AgentConfig":
        """从配置文件加载配置"""
        config = cls()
        logger.debug("Agent 配置加载完成")
        return config

    def validate(self) -> bool:
        """验证配置有效性"""
        if not self.api_key:
            logger.error("LLM API 密钥未配置")
            return False
        return True
