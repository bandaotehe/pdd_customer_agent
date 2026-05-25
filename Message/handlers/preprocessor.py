"""
消息预处理器
提取和优化消息预处理逻辑
"""

import json
from typing import Dict, Any, Union, Optional
from utils.logger_loguru import get_logger
from bridge.context import ContextType


logger = get_logger(__name__)


class MessagePreprocessor:
    """消息预处理器 - 提取通用逻辑"""

    @staticmethod
    def safe_parse_json(data: Any, default_structure: Dict[str, str] = None) -> Dict[str, str]:
        """安全解析JSON，统一处理各种消息格式"""
        if default_structure is None:
            default_structure = {}

        if not data:
            return default_structure

        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else {"raw_content": data, **default_structure}
            except json.JSONDecodeError:
                return {"raw_content": data, **default_structure}
        elif isinstance(data, dict):
            return data
        else:
            return {"raw_content": str(data), **default_structure}

    @staticmethod
    def create_text_message(text: str) -> str:
        """创建标准文本消息格式"""
        return json.dumps([{"type": "text", "text": text}], ensure_ascii=False)

    @staticmethod
    def create_image_message(url: str) -> str:
        """创建标准图片消息格式"""
        return json.dumps([{"type": "image", "url": url}], ensure_ascii=False)

    @staticmethod
    def create_video_message(url: str, cover: str = None) -> str:
        """创建标准视频消息格式"""
        data = {"type": "video", "url": url}
        if cover:
            data["cover"] = cover
        return json.dumps([data], ensure_ascii=False)

    @staticmethod
    def create_goods_message(name: str, price: str = None, thumb_url: str = None, goods_id: str = None, **kwargs) -> str:
        """创建标准商品消息格式"""
        data = {"type": "goods_card", "name": name}
        if price: data["price"] = price
        if thumb_url: data["thumb_url"] = thumb_url
        if goods_id: data["goods_id"] = goods_id
        data.update(kwargs)
        return json.dumps([data], ensure_ascii=False)

    @staticmethod
    def create_order_message(order_sn: str, status: str = None, goods_name: str = None, **kwargs) -> str:
        """创建标准订单消息格式"""
        data = {"type": "order_info", "order_sn": order_sn}
        if status: data["status"] = status
        if goods_name: data["goods_name"] = goods_name
        data.update(kwargs)
        return json.dumps([data], ensure_ascii=False)

    def process(self, content: str, msg_type: Optional[ContextType] = None) -> str:
        """统一的消息预处理"""
        try:
            # 根据消息类型进行特定处理
            if msg_type == ContextType.IMAGE:
                return "[图片消息]"
            elif msg_type == ContextType.VIDEO:
                return "[视频消息]"

            # 1. 尝试解析为JSON
            parsed = self.safe_parse_json(content)

            if isinstance(parsed, dict):
                # 2. 如果是字典，提取关键信息，直接返回纯文本
                processed = self._extract_key_info(parsed)
                if processed:
                    return processed

            # 3. 清理文本，直接返回纯文本
            cleaned = self._clean_text(content)
            return cleaned

        except Exception as e:
            logger.error(f"Message preprocessing failed: {e}")
            return "消息处理失败"

    def _extract_key_info(self, data: Dict[str, Any]) -> str:
        """提取关键信息"""
        parts = []

        # 商品信息
        goods_name = data.get('goods_name') or data.get('name')
        if goods_name:
            parts.append(f"商品：{goods_name}")

        goods_price = data.get('goods_price') or data.get('price')
        if goods_price:
            parts.append(f"价格：{goods_price}")

        goods_spec = data.get('goods_spec') or data.get('spec')
        if goods_spec:
            parts.append(f"规格：{goods_spec}")

        # 商品ID - 保留用于知识库查询
        goods_id = data.get('goods_id')
        if goods_id:
            parts.append(f"商品ID：{goods_id}")

        # 订单信息
        order_id = data.get('order_id') or data.get('order')
        if order_id:
            parts.append(f"订单：{order_id}")

        # 原始内容
        raw_content = data.get('raw_content')
        if raw_content:
            parts.append(f"内容：{raw_content}")

        # 如果没有提取到有效信息，返回原始内容
        if not parts and 'raw_content' in data:
            return data['raw_content']

        return "，".join(parts) if parts else ""

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        if not isinstance(text, str):
            return str(text)

        # 移除多余的空白字符
        cleaned = ' '.join(text.split())

        # 限制长度（避免过长的消息）
        if len(cleaned) > 500:
            cleaned = cleaned[:500] + "..."

        return cleaned