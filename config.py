"""
配置文件管理模块
获取config.json中的配置，提供配置访问接口
提供类型安全、线程安全的配置管理系统
支持配置验证
"""
import json
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Union
from contextlib import contextmanager
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ModelType(str, Enum):
    """模型类型枚举"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    KIMI = "kimi"
    CLAUDE = "claude"

class LLMConfig(BaseModel):
    """LLM 配置模型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    model_name: str = Field(default="", description="模型名称")
    api_key: str = Field(default="", description="API密钥")
    api_base: str = Field(default="", description="API地址")
    supports_vision: bool = Field(default=False, description="是否支持图片/视频输入（视觉模型）")


class BusinessHoursConfig(BaseModel):
    """营业时间配置模型"""
    start: str = Field(default="08:00", description="开始时间")
    end: str = Field(default="23:00", description="结束时间")

    @field_validator('start', 'end')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """验证时间格式 HH:MM"""
        try:
            datetime.strptime(v, '%H:%M')
            return v
        except ValueError:
            raise ValueError('时间格式必须为HH:MM，例如08:00')

class PromptConfig(BaseModel):
    """提示词配置模型"""
    instructions: list[str] = Field(default=[], description="指令")


class OSSConfig(BaseModel):
    """OSS 对象存储配置"""
    access_key_id: str = Field(default="", description="AccessKey ID")
    access_key_secret: str = Field(default="", description="AccessKey Secret")
    endpoint: str = Field(default="oss-cn-hangzhou.aliyuncs.com", description="OSS Endpoint")
    bucket: str = Field(default="", description="Bucket 名称")


class EmbeddingConfig(BaseModel):
    """嵌入模型配置"""
    provider: str = Field(default="openai", description="openai 或 local")
    model_name: str = Field(default="text-embedding-3-small", description="嵌入模型名称")
    api_key: str = Field(default="", description="API密钥，为空则复用 llm.api_key")
    api_base: str = Field(default="", description="API地址，为空则复用 llm.api_base")
    dimension: int = Field(default=1536, ge=1, le=8192, description="嵌入向量维度")


class RerankerConfig(BaseModel):
    """重排序模型配置"""
    provider: str = Field(default="local", description="api 或 local")
    model_name: str = Field(default="BAAI/bge-reranker-v2-m3", description="重排序模型名称")
    api_key: str = Field(default="", description="API密钥")
    api_base: str = Field(default="", description="API地址")


class VectorDBConfig(BaseModel):
    """向量数据库配置"""
    persist_directory: str = Field(default="./temp/vector_db", description="持久化目录")


class KnowledgeBaseConfig(BaseModel):
    """知识库整体配置"""
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    hybrid_search_alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="混合检索权重，1=纯向量，0=纯BM25")
    chunk_size: int = Field(default=500, ge=100, le=2000, description="分块大小（字符）")
    chunk_overlap: int = Field(default=50, ge=0, le=500, description="分块重叠（字符）")


class ConfigModel(BaseModel):
    """配置模型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    business_hours: BusinessHoursConfig = Field(
        default_factory=BusinessHoursConfig,
        description="营业时间配置"
    )
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM配置"
    )
    prompt: PromptConfig = Field(
        default_factory=PromptConfig,
        description="提示词配置"
    )
    db_path: str = Field(default="", description="数据库路径")
    knowledge_base: KnowledgeBaseConfig = Field(
        default_factory=KnowledgeBaseConfig,
        description="知识库配置"
    )
    oss: OSSConfig = Field(
        default_factory=OSSConfig,
        description="OSS 配置"
    )



# 默认配置基础数据
config_base = {
    "db_path": "./temp/channel_shop.db",
    "oss": {
        "access_key_id": "",
        "access_key_secret": "",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "bucket": ""
    },
    "business_hours": {
        "start": "08:00",
        "end": "23:00"
    },
    "llm": {
        "model_name": "",
        "api_key": "",
        "api_base": ""
    },
    "prompt": {
        "instructions": [
            "1. 始终用中文回复，热情亲切，称呼用户为「亲」",
            "2. 回复精炼，控制在 2-3 句以内",
            "3. ⚠️ 安全兜底：涉及用药/服用方法/用法用量/禁忌等问题时，禁止调用 get_product_knowledge 商品知识库，这类固定话术请通过 search_customer_service_knowledge 从知识库获取",
            "4. 先理解用户需求再作答：优先查知识库，知识库有内容时直接引用原文回复，严禁自行发挥、曲解或补充，无则凭经验回答，不确定时引导转人工",
            "5. 涉及具体商品的成分、功效、规格等非安全性信息时，使用 get_product_knowledge；涉及物流/发货/退换货政策/FAQ/使用说明等售前问题时，使用 search_customer_service_knowledge 检索知识库（含客服知识 + 自定义知识）",
            "6. 推荐商品时，先介绍商品亮点让用户自行判断，用户明确要求发送卡片时再调用 send_goods_link",
            "7. 用户明确要求转人工时，调用 transfer_conversation（工作时间 8:00-23:00 内）",
            "8. 禁止出现任何例如😊等emoji表情，禁止出现～这种语气后缀，你只需要语气和善的回答用户的消息"
        ]
    },
    "knowledge_base": {
        "embedding": {
            "provider": "openai",
            "model_name": "text-embedding-3-small",
            "api_key": "",
            "api_base": "",
            "dimension": 1536
        },
        "reranker": {
            "provider": "local",
            "model_name": "BAAI/bge-reranker-v2-m3",
            "api_key": "",
            "api_base": ""
        },
        "vector_db": {
            "persist_directory": "./temp/vector_db"
        },
        "hybrid_search_alpha": 0.5,
        "chunk_size": 500,
        "chunk_overlap": 50
    }
}



class ConfigError(Exception):
    """配置相关错误的基类"""
    pass


class ConfigFileNotFoundError(ConfigError):
    """配置文件未找到错误"""
    pass


class ConfigParseError(ConfigError):
    """配置文件解析错误"""
    pass


class ConfigValidationError(ConfigError):
    """配置验证错误"""
    pass


class Config:
    """
    线程安全的配置管理器

    特性：
    - 类型安全的配置访问
    - 配置验证
    - 线程安全
    - 异常处理完善
    """

    def __init__(
        self,
        config_path: Union[str, Path] = 'config.json',
        auto_create: bool = True
    ):
        """
        初始化配置类

        Args:
            config_path: 配置文件路径
            auto_create: 是否自动创建默认配置文件
        """
        self.config_path = Path(config_path)
        self.auto_create = auto_create

        # 线程安全锁
        self._lock = threading.RLock()

        # 配置缓存
        self._config: Optional[Dict[str, Any]] = None
        self._validated_config: Optional[ConfigModel] = None

        # 加载配置
        self.reload()

    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置"""
        if not self.config_path.exists():
            raise ConfigFileNotFoundError(f"配置文件不存在: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 验证配置格式
            validated_config = ConfigModel(**config_data)
            self._validated_config = validated_config

            return config_data
        except json.JSONDecodeError as e:
            raise ConfigParseError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ConfigValidationError(f"配置验证失败: {e}")

    def _create_default_config_file(self) -> None:
        """创建默认配置文件"""
        try:
            # 创建目录（如果不存在）
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_base, f, ensure_ascii=False, indent=4)

            print(f"已创建默认配置文件：{self.config_path}")
        except Exception as e:
            raise ConfigError(f"创建配置文件失败: {e}")

    def reload(self) -> Dict[str, Any]:
        """重新加载配置文件"""
        with self._lock:
            try:
                self._config = self._load_config()
                return self._config
            except ConfigFileNotFoundError:
                if self.auto_create:
                    self._create_default_config_file()
                    self._config = config_base.copy()
                    self._validated_config = ConfigModel(**config_base)
                    return self._config
                else:
                    raise
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                # 使用默认配置
                self._config = config_base.copy()
                self._validated_config = ConfigModel(**config_base)
                return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号分隔的嵌套访问

        Args:
            key: 配置键名，支持嵌套访问如 'llm.api_key'
            default: 默认值

        Returns:
            配置值
        """
        with self._lock:
            if self._config is None:
                return default

            try:
                keys = key.split('.')
                value = self._config

                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        return default

                return value
            except Exception:
                return default

    def get_model(self) -> ConfigModel:
        """获取验证后的配置模型"""
        with self._lock:
            return self._validated_config or ConfigModel()

    def __getitem__(self, key: str) -> Any:
        """支持使用字典方式访问配置"""
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        """支持使用 in 操作符检查配置项是否存在"""
        with self._lock:
            if self._config is None:
                return False
            keys = key.split('.')
            value = self._config
            for k in keys:
                if not isinstance(value, dict) or k not in value:
                    return False
                value = value[k]
            return True

    def set(self, key: str, value: Any, save: bool = True) -> Any:
        """
        设置配置项

        Args:
            key: 配置项键名
            value: 配置项值
            save: 是否立即保存到文件，默认为True

        Returns:
            设置的值
        """
        with self._lock:
            if self._config is None:
                self._config = config_base.copy()

            # 解析嵌套键
            keys = key.split('.')
            current = self._config

            # 导航到目标位置
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]

            # 设置值
            current[keys[-1]] = value

            # 重新验证配置
            try:
                self._validated_config = ConfigModel(**self._config)
                if save:
                    self.save()
            except Exception as e:
                raise ConfigValidationError(f"设置配置项失败: {e}")

            return value

    def update(self, config_dict: Dict[str, Any], save: bool = False) -> Dict[str, Any]:
        """
        批量更新配置

        Args:
            config_dict: 包含多个配置项的字典
            save: 是否立即保存到文件，默认为False

        Returns:
            更新后的完整配置
        """
        with self._lock:
            if self._config is None:
                self._config = config_base.copy()

            # 深度合并配置
            merged_config = self._deep_merge(self._config, config_dict)

            try:
                self._validated_config = ConfigModel(**merged_config)
                self._config = merged_config
                if save:
                    self.save()
                return self._config
            except Exception as e:
                raise ConfigValidationError(f"批量更新配置失败: {e}")

    def save(self) -> bool:
        """将当前配置原子性地保存到文件（临时文件+重命名）"""
        with self._lock:
            if self._config is None:
                raise ConfigError("没有可保存的配置")

            try:
                # 创建目录（如果不存在）
                self.config_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用临时文件 + 原子重命名，避免写入过程中崩溃导致配置文件损坏
                temp_path = self.config_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=4)

                # 原子重命名替换原文件
                temp_path.replace(self.config_path)
                return True
            except Exception as e:
                print(f"保存配置文件失败: {e}")
                # 清理临时文件（如果存在）
                try:
                    temp_path = self.config_path.with_suffix('.tmp')
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception:
                    pass
                return False

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()

        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    @contextmanager
    def atomic_update(self):
        """原子性更新配置的上下文管理器"""
        import copy
        original_config = copy.deepcopy(self._config) if self._config else None
        original_validated = copy.deepcopy(self._validated_config)
        try:
            yield self
            self.save()
        except Exception:
            # 回滚到原始配置
            if original_config is not None:
                self._config = original_config
                self._validated_config = original_validated
            raise

# 创建全局配置实例
config = Config()


# ==============================
# 便捷函数
# ==============================

def get_config(key: str, default: Any = None) -> Any:
    """全局便捷函数：获取配置项"""
    return config.get(key, default)


def set_config(key: str, value: Any, save: bool = False) -> Any:
    """全局便捷函数：设置配置项"""
    return config.set(key, value, save)


def reload_config() -> Dict[str, Any]:
    """全局便捷函数：重新加载配置"""
    return config.reload()


def save_config() -> bool:
    """全局便捷函数：保存配置"""
    return config.save()


def update_config(config_dict: Dict[str, Any], save: bool = False) -> Dict[str, Any]:
    """全局便捷函数：批量更新配置"""
    return config.update(config_dict, save)


def get_validated_config() -> ConfigModel:
    """全局便捷函数：获取验证后的配置模型"""
    return config.get_model()

