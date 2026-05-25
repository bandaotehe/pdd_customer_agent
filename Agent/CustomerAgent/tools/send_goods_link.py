"""
发送商品卡片工具
"""
from typing import Optional, Union
from pydantic import BaseModel, Field

from Agent.CustomerAgent.custom.tool_decorator import agent_tool
from Channel.pinduoduo.utils.API.send_message import SendMessage
from utils.logger_loguru import get_logger

logger = get_logger("SendGoodsLinkTool")


class SendGoodsLinkParams(BaseModel):
    """发送商品卡片参数"""
    recipient_uid: Optional[str] = Field(default=None, description="接收消息的用户UID")
    goods_id: Optional[int] = Field(default=None, description="商品ID。必须使用商品列表中给出的 商品ID（通常是很大的数字）。绝对不能使用列表序号(1, 2, 3...)，那是错误的！")
    shop_id: Optional[Union[str, int]] = Field(default=None, description="店铺ID")
    user_id: Optional[Union[str, int]] = Field(default=None, description="用户ID（账号ID）")


@agent_tool(
    name="send_goods_link",
    description="向用户发送商品卡片链接，用于客服主动推荐商品。重要：goods_id 必须使用商品列表中给出的真实商品ID（大数），严禁使用列表序号（1、2、3这样的小数）！",
    param_model=SendGoodsLinkParams,
)
def send_goods_link(params: SendGoodsLinkParams) -> str:
    try:
        logger.info(f"[Card Step 0] 入参: goods_id={params.goods_id} shop_id={params.shop_id} "
                    f"user_id={params.user_id} recipient_uid={params.recipient_uid}")

        if not all([params.recipient_uid, params.goods_id, params.shop_id, params.user_id]):
            missing = [k for k, v in {"recipient_uid": params.recipient_uid, "goods_id": params.goods_id,
                                       "shop_id": params.shop_id, "user_id": params.user_id}.items() if not v]
            logger.error(f"[Card Step 0] 缺少参数: {missing}")
            return "发送失败：缺少必要参数，请用文字回答用户即可"

        if params.goods_id is not None and params.goods_id < 1000:
            logger.warning(f"[Card Step 0] goods_id={params.goods_id} 太小，可能误用了列表序号")
            return f"goods_id={params.goods_id} 无效，请使用商品列表中「商品ID」标签后面的真实大数字"

        # Step 1: 创建 sender
        logger.info(f"[Card Step 1] 创建 SendMessage: shop_id={params.shop_id} user_id={params.user_id}")
        sender = SendMessage(str(params.shop_id), str(params.user_id))

        # Step 2: 发送卡片
        logger.info(f"[Card Step 2] 调用 send_mallGoodsCard: recipient={params.recipient_uid} "
                    f"goods_id={params.goods_id} biz_type=2")
        result = sender.send_mallGoodsCard(params.recipient_uid, params.goods_id, biz_type=2)
        logger.info(f"[Card Step 2] send_mallGoodsCard 返回: {result}")

        if result and result.get("success"):
            logger.info(f"[Card DONE] 商品卡片发送成功: goods_id={params.goods_id}")
            return "商品卡片发送成功"
        else:
            error_msg = result.get('error_msg', '发送失败') if result else '发送失败'
            logger.error(f"[Card FAIL] 卡片发送失败: {error_msg}")
            return "商品卡片发送失败（后台已记录），请用文字回答用户即可"
    except Exception as e:
        logger.error(f"发送商品卡片异常: {e}", exc_info=True)
        return "发送异常（后台已记录），请用文字回答用户即可"
