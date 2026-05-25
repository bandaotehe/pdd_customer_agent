"""
上下文类型枚举和Pydantic模型定义
"""
from enum import Enum
from typing import Optional, Dict, Any, Union, List
from pydantic import BaseModel, Field

class ChannelType(str, Enum):
    """渠道类型枚举"""
    PINDUODUO = "pinduoduo"
    JINGDONG = "jingdong"
    TAOBAO = "taobao"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"

    def __str__(self):
        return self.value

class ContextType(str, Enum):
    """上下文类型枚举"""
    TEXT = "text"  # 文本
    IMAGE = "image"  # 图片
    VIDEO = "video"  # 视频
    EMOTION = "emotion"  # 表情
    GOODS_CARD = "goods_card"  # 商品卡片
    GOODS_INQUIRY = "goods_inquiry"  # 商品规格咨询
    GOODS_SPEC = "goods_spec"  # 商品规格
    ORDER_INFO = "order_info"  # 订单信息
    SYSTEM_STATUS = "system_status"  # 系统状态
    MALL_SYSTEM_MSG = "mall_system_msg"  # 商城消息
    SYSTEM_HINT = "system_hint"  # 系统提示
    SYSTEM_BIZ = "system_biz"  # 系统业务
    MALL_CS = "mall_cs"  # 商城客服
    WITHDRAW = "withdraw"  # 撤回
    AUTH = "auth"  # 认证
    TRANSFER = "transfer"  # 转接

    def __str__(self):
        return self.value

class PinduoduoKwargs(BaseModel):
    """拼多多消息专用kwargs类型定义"""
    msg_id: Optional[str] = None
    shop_name: Optional[str] = None
    from_user: Optional[str] = None
    from_uid: Optional[str] = None
    to_user: Optional[str] = None
    to_uid: Optional[str] = None
    nickname: Optional[str] = None
    timestamp: Optional[str] = None
    user_msg_type: Optional[ContextType] = None
    shop_id: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    goods_id: Optional[str] = None
    goods_name: Optional[str] = None
    goods_price: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True

class Context(BaseModel):
    """上下文模型，使用Pydantic进行数据验证"""
    type: ContextType = Field(..., description="上下文类型")
    content: Optional[str] = Field(None, description="内容")
    media_urls: List[str] = Field(default_factory=list, description="图片/视频 URL 列表")
    kwargs: Any = Field(default_factory=dict, description="渠道专用参数")
    channel_type: Optional[ChannelType] = Field(None, description="渠道类型")

    @classmethod
    def create_pinduoduo_context(cls, content=None, msg_id=None, from_user=None, from_uid=None,
                                to_user=None, to_uid=None, nickname=None, timestamp=None,
                                user_msg_type=None, shop_id=None, user_id=None, username=None, shop_name=None,
                                goods_id=None, goods_name=None, goods_price=None,
                                raw_data=None, channel_type=None, media_urls=None):
        """创建拼多多上下文实例的便捷方法"""
        kwargs = PinduoduoKwargs(
            msg_id=msg_id,
            from_user=from_user,
            from_uid=from_uid,
            to_user=to_user,
            to_uid=to_uid,
            nickname=nickname,
            timestamp=timestamp,
            user_msg_type=user_msg_type,
            shop_id=shop_id,
            user_id=user_id,
            username=username,
            shop_name=shop_name,
            goods_id=goods_id,
            goods_name=goods_name,
            goods_price=goods_price,
            raw_data=raw_data
        )

        return cls(
            type=user_msg_type or ContextType.TEXT,
            content=content,
            media_urls=media_urls or [],
            kwargs=kwargs,
            channel_type=channel_type
        )

