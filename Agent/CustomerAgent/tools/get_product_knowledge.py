"""
获取产品知识工具
================

根据商品ID或关键词获取产品详细知识。
"""
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator, field_validator
from Agent.CustomerAgent.custom.tool_decorator import agent_tool

from database.knowledge_service import KnowledgeService
from core.di_container import container

# 从DI容器获取服务实例
knowledge_service = container.get(KnowledgeService)


class GetProductKnowledgeParams(BaseModel):
    """获取产品知识参数（goods_id 和 query 二选一）"""
    goods_id: Optional[int] = Field(default=None, description="商品ID（精确查询时使用）")
    query: Optional[str] = Field(default=None, description="搜索关键词（模糊搜索时使用，从用户原话提炼核心词）")
    shop_id: int = Field(..., description="店铺ID（必须提供）")

    @field_validator('goods_id', mode='before')
    @classmethod
    def coerce_empty_to_none(cls, v: Any) -> Any:
        """LLM 可能传空字符串 '' 作为 goods_id，转为 None"""
        if v is None or v == '' or v == 0:
            return None
        return v

    @model_validator(mode='after')
    def check_at_least_one(self):
        if not self.goods_id and not self.query:
            raise ValueError('goods_id 和 query 必须提供至少一个')
        return self


@agent_tool(
    name="get_product_knowledge",
    description="获取产品知识。有两种用法：1) 已知商品ID时传 goods_id 精确查询；2) 用户描述商品特征/名称但不知道ID时传 query 关键词模糊搜索（如用户问「有没有XX成分的」「补水保湿的」→query='补水保湿'）。两种用法都需要传 shop_id。",
    param_model=GetProductKnowledgeParams,
)
def get_product_knowledge(params: GetProductKnowledgeParams) -> str:
    """
    获取产品知识

    Args:
        params: GetProductKnowledgeParams
            goods_id: 商品ID（精确查询）
            query: 搜索关键词（模糊搜索）
            shop_id: 店铺ID

    Returns:
        格式化的产品知识
    """
    if not params.shop_id:
        return "[错误：缺少店铺ID，无法获取产品知识]"

    if params.goods_id:
        # 精确查询
        result = knowledge_service.search_knowledge(
            shop_id=params.shop_id,
            query=None,
            goods_id=params.goods_id,
        )
    elif params.query:
        # 关键词模糊搜索
        result = knowledge_service.search_knowledge(
            shop_id=params.shop_id,
            query=params.query,
            goods_id=None,
        )
    else:
        return "[错误：请提供 goods_id 或 query 参数]"

    return knowledge_service.format_search_result(result)
