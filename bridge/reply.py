"""
回复类型枚举
"""
from enum import Enum


class ReplyType(Enum):
    TEXT = 1  # 文本
    IMAGE = 2  # 图片文件
    IMAGE_URL = 3  # 图片URL
    VIDEO_URL = 4  # 视频URL
    FILE = 5  # 文件
    LINK = 6  # 链接
    ERROR = 7  # 内部错误（不应返回给客户）

    def __str__(self):
        return self.name


class Reply:
    def __init__(self, type: ReplyType = None, content=None):
        self.type = type
        self.content = content

    def __str__(self):
        return "Reply(type={}, content={})".format(self.type, self.content)