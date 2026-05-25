"""
工具执行器模块

负责并行执行 Agent 工具调用。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from utils.logger_loguru import get_logger
from Agent.CustomerAgent.custom.tool_decorator import execute_tool

logger = get_logger("ToolExecutor")


class ToolResult:
    """工具执行结果"""

    def __init__(self, tool_call_id: str, content: str):
        self.tool_call_id = tool_call_id
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        """转换为 LLM 消息格式的字典"""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


class ToolExecutor:
    """工具执行器"""
    pass

    async def execute_parallel(
        self,
        tool_calls: List[Any],
        dependencies: Dict[str, Any],
    ) -> List[ToolResult]:
        """
        并行执行多个工具调用

        Args:
            tool_calls: 工具调用列表
            dependencies: 依赖字典

        Returns:
            工具执行结果列表（按原始顺序）
        """
        if not tool_calls:
            return []

        logger.debug(f"开始并行执行 {len(tool_calls)} 个工具")

        # 构建任务列表
        tasks: List[Any] = []
        for tc in tool_calls:
            task = asyncio.get_event_loop().run_in_executor(
                None,
                execute_tool,
                tc.function.name,
                tc.function.arguments,
                dependencies,
            )
            tasks.append((tc.id, task))

        # 等待所有任务完成
        results: List[ToolResult] = []
        for tool_call_id, task in tasks:
            try:
                content = await task
                results.append(ToolResult(tool_call_id, content))
                logger.debug(f"工具执行完成: {tool_call_id}")
            except Exception as e:
                logger.error(f"工具执行失败: {tool_call_id}, error: {e}")
                results.append(ToolResult(tool_call_id, f"[工具执行错误: {e}]"))

        # 按原始顺序排列
        tool_ids = [tc.id for tc in tool_calls]
        results.sort(key=lambda r: tool_ids.index(r.tool_call_id))

        return results

    def results_to_messages(self, results: List[ToolResult]) -> List[Dict[str, str]]:
        """
        将工具执行结果转换为 LLM 消息格式

        Args:
            results: 工具执行结果列表

        Returns:
            LLM 消息格式的结果列表
        """
        return [result.to_dict() for result in results]
