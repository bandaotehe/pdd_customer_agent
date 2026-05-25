"""
搜索客服知识工具
====================

根据关键词和店铺ID搜索客服知识。
"""
from typing import Optional
from pydantic import BaseModel, Field
from Agent.CustomerAgent.custom.tool_decorator import agent_tool

from database.knowledge_service import KnowledgeService
from core.di_container import container

# 从DI容器获取服务实例
knowledge_service = container.get(KnowledgeService)


class SearchCustomerServiceKnowledgeParams(BaseModel):
    """搜索客服知识参数"""
    query: str = Field(..., description="搜索关键词（必须提供）")
    shop_id: int = Field(..., description="店铺ID（必须提供）")


@agent_tool(
    name="search_customer_service_knowledge",
    description="搜索客服知识库，查找物流政策、发货时间、常见问题解答等售前客服知识。当用户询问物流、发货、使用说明、退换货政策等售前相关问题时使用此工具。",
    param_model=SearchCustomerServiceKnowledgeParams,
)
def search_customer_service_knowledge(params: SearchCustomerServiceKnowledgeParams) -> str:
    """
    搜索客服知识

    Args:
        params: SearchCustomerServiceKnowledgeParams
            query: 搜索关键词
            shop_id: 店铺ID

    Returns:
        格式化的客服知识
    """
    if not params.shop_id:
        return "[错误：缺少店铺ID，无法搜索客服知识]"

    if not params.query:
        return "[错误：缺少搜索关键词，无法搜索客服知识]"

    result = knowledge_service.search_knowledge(
        shop_id=params.shop_id,
        query=params.query,
        goods_id=None,
    )

    return knowledge_service.format_search_result(result)
