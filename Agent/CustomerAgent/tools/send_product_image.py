"""
发送产品图片工具 — 读取产品知识库中已上传的图片 URL，直接发送给用户
"""
from typing import Optional, Union
from pydantic import BaseModel, Field

from Agent.CustomerAgent.custom.tool_decorator import agent_tool
from Channel.pinduoduo.utils.API.send_message import SendMessage
from database.knowledge_service import KnowledgeService
from core.di_container import container
from utils.logger_loguru import get_logger

logger = get_logger("SendProductImageTool")


class SendProductImageParams(BaseModel):
    """发送产品图片参数"""
    goods_id: Optional[int] = Field(default=None, description="商品 ID")
    recipient_uid: Optional[str] = Field(default=None, description="接收消息的用户 UID")
    shop_id: Optional[Union[str, int]] = Field(default=None, description="店铺 ID")
    user_id: Optional[Union[str, int]] = Field(default=None, description="账号 ID")


@agent_tool(
    name="send_product_image",
    description="发送产品说明书图片给用户。当用户询问用法、说明书等问题时，先用文字简要回复，再调用此工具发送产品图片。",
    param_model=SendProductImageParams,
)
def send_product_image(params: SendProductImageParams) -> str:
    try:
        logger.info(f"[Step 0] 入参: goods_id={params.goods_id} shop_id={params.shop_id} "
                    f"user_id={params.user_id} recipient_uid={params.recipient_uid}")

        if not all([params.recipient_uid, params.goods_id, params.shop_id, params.user_id]):
            missing = []
            if not params.recipient_uid: missing.append("recipient_uid")
            if not params.goods_id: missing.append("goods_id")
            if not params.shop_id: missing.append("shop_id")
            if not params.user_id: missing.append("user_id")
            logger.error(f"[Step 0] 缺少参数: {missing}")
            return "参数不完整（后台已记录），回复时正常回答用户问题即可"

        # Step 1: 查产品
        logger.info(f"[Step 1] 查询产品: shop_id={params.shop_id} goods_id={params.goods_id}")
        try:
            ks = container.get(KnowledgeService)
        except Exception as e:
            logger.warning(f"[Step 1] DI 容器获取 KnowledgeService 失败: {e}，创建新实例")
            ks = KnowledgeService()
        result = ks.search_knowledge(int(params.shop_id), goods_id=params.goods_id)
        products = result.get("product_knowledge", [])
        product = products[0] if products else None
        logger.info(f"[Step 1] 查询结果: found={product is not None} "
                    f"image_path={repr(product.image_path) if product else 'None'}")

        if not product:
            logger.warning(f"[Step 1] 产品不存在: goods_id={params.goods_id}")
            return "商品未找到（后台已记录），回复时正常回答用户问题即可"
        if not product.image_path:
            logger.warning(f"[Step 1] 产品无图片: goods_id={params.goods_id} goods_name={product.goods_name}")
            return "该商品暂无说明书图片，回复时正常回答用户问题即可，不要提及图片发送失败"

        # Step 2: 本地路径
        local_path = product.image_path
        logger.info(f"[Step 2] 图片路径: {local_path}")
        if local_path.startswith("http"):
            logger.info(f"[Step 2] 是 OSS URL，下载到临时文件...")
            from pathlib import Path
            import tempfile, requests
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=Path(local_path).suffix or ".png", delete=False)
                resp = requests.get(local_path, timeout=30)
                tmp.write(resp.content)
                tmp.close()
                local_path = tmp.name
                logger.info(f"[Step 2] 下载完成: {local_path} size={len(resp.content)} bytes")
            except Exception as e:
                logger.error(f"[Step 2] 下载 OSS 图片失败: {e}")
                return "图片下载失败（后台已记录），回复时正常回答用户问题即可"

        # Step 3: 上传到 PDD CDN
        logger.info(f"[Step 3] 上传到 PDD CDN: {local_path}")
        sender = SendMessage(str(params.shop_id), str(params.user_id))
        pdd_url = sender.upload_image_to_pdd(local_path)
        if not pdd_url:
            logger.error(f"[Step 3] 上传 PDD CDN 失败")
            return "图片上传失败（后台已记录），回复时正常回答用户问题即可，不要提及图片发送失败"
        logger.info(f"[Step 3] 上传成功: {pdd_url}")

        # Step 4: 发送图片消息
        logger.info(f"[Step 4] 发送图片消息: recipient={params.recipient_uid} url={pdd_url}")
        result = sender.send_image(params.recipient_uid, pdd_url)
        logger.info(f"[Step 4] send_image 返回: {result}")
        if result and result.get("success"):
            logger.info(f"[DONE] 产品图片发送成功: goods_id={params.goods_id}")
            return "产品图片发送成功"
        else:
            logger.error(f"[Step 4] 图片发送失败: result={result}")
            return "图片消息发送失败（后台已记录），回复时正常回答用户问题即可，不要提及图片发送失败"
    except Exception as e:
        logger.error(f"发送产品图片异常: {e}", exc_info=True)
        return "图片发送异常（后台已记录），回复时正常回答用户问题即可，不要提及发送失败"
