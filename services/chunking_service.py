"""
文本智能分块服务
递归字符分割：优先在自然语义边界处切分，保证每块不超过 chunk_size 字符。
"""
import re
from typing import List, Dict
from utils.logger_loguru import get_logger

logger = get_logger("ChunkingService")


class ChunkingService:
    """递归字符级文本分块器"""

    # 分隔符优先级：从粗到细
    _SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = max(chunk_size, 100)
        self.chunk_overlap = min(chunk_overlap, self.chunk_size // 2)

    def chunk_text(self, text: str) -> List[str]:
        """将文本切分为固定大小的块"""
        if not text or not text.strip():
            return []
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        self._recursive_split(text, chunks)
        return chunks

    def _recursive_split(self, text: str, result: List[str], depth: int = 0):
        """递归分割"""
        if len(text) <= self.chunk_size:
            result.append(text)
            return

        separator = self._SEPARATORS[min(depth, len(self._SEPARATORS) - 1)]

        if separator:
            parts = text.split(separator)
            if len(parts) == 1:
                # 无此分隔符，降到下一级
                self._recursive_split(text, result, depth + 1)
                return
        else:
            # 字符级强制切分
            for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
                chunk = text[i:i + self.chunk_size]
                if chunk:
                    result.append(chunk)
            return

        # 带重叠地拼接 parts
        current_chunk = ""
        for part in parts:
            # 先尝试加入当前 chunk
            candidate = current_chunk + (separator if current_chunk else "") + part
            if len(candidate) <= self.chunk_size:
                current_chunk = candidate
            else:
                # 当前 chunk 已满，保存
                if current_chunk:
                    result.append(current_chunk)
                # 如果单个 part 仍然超长，递归
                if len(part) > self.chunk_size:
                    self._recursive_split(part, result, depth + 1)
                    current_chunk = ""
                else:
                    # 从上一块的末尾取 overlap
                    if result and self.chunk_overlap > 0:
                        overlap_text = result[-1][-self.chunk_overlap:]
                        current_chunk = overlap_text + separator + part if overlap_text else part
                    else:
                        current_chunk = part

        if current_chunk:
            result.append(current_chunk)

    def preview_chunks(self, text: str) -> List[Dict]:
        """预览分块结果，供 UI 展示"""
        chunks = self.chunk_text(text)
        return [
            {"index": i, "text": chunk, "length": len(chunk)}
            for i, chunk in enumerate(chunks)
        ]
