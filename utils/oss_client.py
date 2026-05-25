"""阿里云 OSS 上传工具"""
from pathlib import Path
from config import get_config
from utils.logger_loguru import get_logger

logger = get_logger("OSSClient")


def upload_to_oss(local_path: str) -> str | None:
    """上传文件到 OSS，返回公网 URL。失败返回 None。"""
    import oss2

    ak = get_config("oss.access_key_id", "")
    sk = get_config("oss.access_key_secret", "")
    endpoint = get_config("oss.endpoint", "oss-cn-hangzhou.aliyuncs.com")
    bucket_name = get_config("oss.bucket", "")

    if not ak or not sk or not bucket_name:
        logger.error("OSS 配置不完整，请检查 config.json 中 oss.access_key_id / access_key_secret / bucket")
        return None

    local = Path(local_path)
    if not local.exists():
        logger.error(f"图片文件不存在: {local_path}")
        return None

    try:
        auth = oss2.Auth(ak, sk)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        object_name = f"product-images/{local.name}"
        bucket.put_object_from_file(object_name, str(local))

        # 构造公网 URL
        url = f"https://{bucket_name}.{endpoint}/{object_name}"
        logger.info(f"图片上传成功: {local.name} → {url}")
        return url
    except Exception as e:
        logger.error(f"OSS 上传失败: {e}")
        return None
