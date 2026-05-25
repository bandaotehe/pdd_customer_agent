"""
编码转换工具
处理不同编码的文本文件，统一转换为 UTF-8
"""
import os
import tempfile
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class EncodingConverter:
    """编码转换工具类"""

    # 常见中文编码列表
    ENCODINGS = ['utf-8', 'gbk', 'gb18030', 'gb2312', 'big5', 'shift_jis']

    @staticmethod
    def ensure_utf8(file_path: str) -> Tuple[str, str]:
        """
        确保文件使用UTF-8编码，如果不是则转换

        Args:
            file_path: 原始文件路径

        Returns:
            (文件路径, 检测到的编码)
            如果已UTF-8编码，返回原路径；否则返回临时文件路径
        """
        try:
            # 读取文件原始数据
            with open(file_path, 'rb') as f:
                raw_data = f.read()

            # 尝试不同编码
            content, detected_encoding = EncodingConverter._try_decode(raw_data)

            # 如果已经是UTF-8，直接返回
            if detected_encoding == 'utf-8':
                return file_path, 'utf-8'

            # 创建临时文件
            return EncodingConverter._create_temp_file(content, file_path), detected_encoding

        except Exception as e:
            logger.warning(f"编码转换失败，使用原文件: {e}")
            return file_path, 'unknown'

    @staticmethod
    def _try_decode(raw_data: bytes) -> Tuple[str, str]:
        """
        尝试用不同编码解码数据

        Args:
            raw_data: 原始字节数据

        Returns:
            (解码后的文本, 检测到的编码)
        """
        content = None
        detected_encoding = None

        for encoding in EncodingConverter.ENCODINGS:
            try:
                content = raw_data.decode(encoding)
                detected_encoding = encoding
                logger.info(f"使用 {encoding} 编码成功读取文件")
                break
            except (UnicodeDecodeError, LookupError):
                continue

        # 如果所有编码都失败，使用忽略错误的方式
        if content is None:
            content = raw_data.decode('utf-8', errors='ignore')
            detected_encoding = 'utf-8 (ignore errors)'
            logger.warning("使用忽略错误的方式读取文件")

        return content, detected_encoding

    @staticmethod
    def _create_temp_file(content: str, original_path: str) -> str:
        """
        创建UTF-8编码的临时文件

        Args:
            content: 文件内容
            original_path: 原始文件路径

        Returns:
            临时文件路径
        """
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=os.path.splitext(original_path)[1],
            prefix='utf8_'
        )

        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"已创建UTF-8编码临时文件: {temp_path}")
        return temp_path
