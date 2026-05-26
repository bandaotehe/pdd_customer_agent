"""
获取店铺商品列表工具

用于客服主动推荐商品。
"""
from typing import Optional, Union
from pydantic import BaseModel, Field

from Agent.CustomerAgent.custom.tool_decorator import agent_tool
from Channel.pinduoduo.utils.API.product_manager import ProductManager
from utils.logger_loguru import get_logger

logger = get_logger("GetProductListTool")


class GetShopProductsParams(BaseModel):
    """获取商品列表参数（由 dependencies 自动注入）"""
    shop_id: Optional[Union[str, int]] = Field(default=None, description="店铺ID")
    user_id: Optional[Union[str, int]] = Field(default=None, description="用户ID（账号ID）")
    page: int = Field(default=1, description="页码，从1开始，默认第1页")


@agent_tool(
    name="get_shop_products",
    description="获取店铺商品列表，用于客服主动推荐。",
    param_model=GetShopProductsParams,
)
def get_shop_products(params: GetShopProductsParams) -> str:
    """
    获取店铺商品列表，用于客服主动推荐。

    Returns:
        str: 格式化的商品列表信息，包含商品名称、ID、价格、销量、库存等
    """
    try:
        if not params.shop_id or not params.user_id:
            return "获取商品列表失败：缺少必要的shop_id或user_id参数"

        # 初始化ProductManager，传入shop_id和user_id以获取正确的cookies
        product_manager = ProductManager(shop_id=params.shop_id, user_id=params.user_id)

        # 调用API获取商品列表
        page = params.page if params.page else 1
        result = product_manager.get_product_list(
            page=page,
            size=50
        )

        if result.get("success"):
            products = result.get("products", [])
            total = result.get("total", 0)

            if not products:
                logger.info(f"获取商品列表完成，但店铺当前暂无商品 (shop_id: {params.shop_id})")
                return f"店铺当前暂无商品 (shop_id: {params.shop_id})"

            logger.info(f"获取商品列表成功: shop_id={params.shop_id}, total={total}, page={page}, returned={len(products)}")
            return _format_products_output(products, total, page=page)

        else:
            error_msg = result.get("error_msg", "未知错误")
            logger.error(f"获取商品列表失败: {error_msg}, shop_id={params.shop_id}")
            return f"获取商品列表失败: {error_msg}"

    except Exception as e:
        logger.error(f"获取商品列表工具执行异常: {str(e)}, shop_id={params.shop_id}")
        return f"获取商品列表时发生异常: {str(e)}"


def _format_products_output(products, total, page):
    """格式化商品列表输出"""
    if not products:
        return "未找到商品"

    output = f"商品列表 (共{total}个商品):\n\n"

    for product in products:
        goods_id = product.get("goods_id", "未知ID")
        goods_name = product.get("goods_name", "未命名商品")
        price = product.get("price", "")

        output += f"商品名称: {goods_name}\n商品ID: {goods_id}\n"
        if price:
            output += f"价格: {price} 元\n"
        output += "\n"

    return output
