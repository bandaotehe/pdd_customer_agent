"""
多模态媒体工具 — 图片/视频下载与编码

用于将客户发来的图片/视频 URL 下载并转为 base64 data URI，
以便以 image_url 格式传给视觉 LLM。
"""
import base64
import os
from typing import Optional, List

import httpx
from utils.logger_loguru import get_logger

logger = get_logger("MediaUtils")

# 常见图片 MIME 类型映射（按扩展名）
_EXT_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

_DOWNLOAD_TIMEOUT = 15.0  # 秒


def _guess_mime_type(url: str, content_type: Optional[str] = None) -> str:
    """根据 URL 扩展名或 Content-Type 推测 MIME"""
    if content_type and content_type.startswith("image/"):
        return content_type.split(";")[0].strip()
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    return _EXT_MIME_MAP.get(ext, "image/jpeg")


async def download_image_bytes(url: str, cookies: Optional[dict] = None) -> Optional[bytes]:
    """下载图片原始字节，失败返回 None"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(cookies=cookies, timeout=_DOWNLOAD_TIMEOUT, verify=False,
                                     follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"下载图片失败 HTTP {resp.status_code}: {url[:120]}")
                return None
            return resp.content
    except Exception as e:
        logger.warning(f"下载图片异常: {e} | url={url[:120]}")
        return None


async def download_image_as_data_uri(url: str, cookies: Optional[dict] = None) -> Optional[str]:
    """下载图片并转为 data URI（base64），失败返回 None"""
    data = await download_image_bytes(url, cookies)
    if not data:
        return None
    mime = _guess_mime_type(url)
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


async def download_images_as_data_uris(
    urls: List[str], cookies: Optional[dict] = None
) -> List[str]:
    """批量下载图片并转为 data URI，失败的条目会被丢弃"""
    results = []
    for url in urls:
        data_uri = await download_image_as_data_uri(url, cookies)
        if data_uri:
            results.append(data_uri)
    return results
