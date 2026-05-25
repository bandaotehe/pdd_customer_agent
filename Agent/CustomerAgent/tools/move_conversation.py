"""
会话转接工具 — 将当前会话转接给人工客服
"""
from typing import Optional, Union
from pydantic import BaseModel, Field

from Agent.CustomerAgent.custom.tool_decorator import agent_tool
from Channel.pinduoduo.utils.API.send_message import SendMessage
from utils.logger_loguru import get_logger

logger = get_logger("TransferConversationTool")


class TransferConversationParams(BaseModel):
    shop_id: Optional[Union[str, int]] = Field(default=None, description="店铺ID")
    user_id: Optional[Union[str, int]] = Field(default=None, description="用户ID（账号ID）")
    recipient_uid: Optional[str] = Field(default=None, description="接收转接的用户UID")


@agent_tool(
    name="transfer_conversation",
    description="将当前会话转接给售后专员。用户涉及售后问题（退换货、退款、投诉、物流异常等）或明确要求转人工时调用。",
    param_model=TransferConversationParams,
)
def transfer_conversation(params: TransferConversationParams) -> str:
    try:
        logger.info(f"[Transfer Step 0] 入参: shop_id={params.shop_id} user_id={params.user_id} "
                    f"recipient_uid={params.recipient_uid}")

        if not all([params.shop_id, params.user_id, params.recipient_uid]):
            missing = [k for k, v in {"shop_id": params.shop_id, "user_id": params.user_id,
                                       "recipient_uid": params.recipient_uid}.items() if not v]
            logger.error(f"[Transfer Step 0] 缺少参数: {missing}")
            return "转接失败：缺少必要参数，请用文字安抚用户（如「亲，暂时无法转接，建议您通过订单页面联系售后专员哦」）"

        # Step 1: 创建 sender
        logger.info(f"[Transfer Step 1] 创建 SendMessage")
        sender = SendMessage(str(params.shop_id), str(params.user_id))

        # Step 2: 获取可转接的客服列表
        logger.info(f"[Transfer Step 2] 获取客服列表...")
        cs_list = sender.getAssignCsList()
        logger.info(f"[Transfer Step 2] 客服列表: type={type(cs_list).__name__} data={cs_list}")

        if not cs_list:
            logger.warning("[Transfer Step 2] 无法获取客服列表")
            return "当前没有可转接的售后专员在线，请用文字安抚用户（如「亲，目前售后专员暂时不在线，建议您稍后再联系我们哦」）"

        # cs_list 可能是 list 或 dict
        if isinstance(cs_list, list):
            available = cs_list
        elif isinstance(cs_list, dict):
            my_cs_uid = f"cs_{params.shop_id}_{params.user_id}"
            available = [uid for uid in cs_list.keys() if uid != my_cs_uid]
        else:
            available = []

        if not available:
            logger.warning(f"[Transfer Step 2] 无可用客服: cs_list={cs_list}")
            return "当前没有可转接的售后专员在线，请用文字安抚用户（如「亲，目前售后专员暂时不在线，建议您稍后再联系我们哦」）"

        # Step 3: 执行转接
        cs_uid = available[0] if isinstance(available, list) else available[0]
        if isinstance(cs_uid, dict):
            cs_uid = cs_uid.get("cs_uid") or cs_uid.get("csid") or str(cs_uid)
        logger.info(f"[Transfer Step 3] 转接会话: recipient={params.recipient_uid} → cs_uid={cs_uid}")

        transfer_result = sender.move_conversation(params.recipient_uid, str(cs_uid))
        logger.info(f"[Transfer Step 3] move_conversation 返回: {transfer_result}")

        if transfer_result and transfer_result.get("success"):
            logger.info(f"[Transfer DONE] 会话转接成功: recipient={params.recipient_uid} → {cs_uid}")
            return "会话转接成功"
        else:
            logger.warning(f"[Transfer FAIL] 转接失败: {transfer_result}")
            return "会话转接失败，请用文字安抚用户（如「亲，暂时无法转接，建议您通过订单页面联系售后专员哦」）"
    except Exception as e:
        logger.error(f"转接异常: {e}", exc_info=True)
        return "转接异常（后台已记录），请用文字安抚用户（如「亲，系统暂时有点问题，建议您通过订单页面联系售后专员哦」）"
