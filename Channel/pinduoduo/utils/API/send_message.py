from ..base_request import BaseRequest
from typing import Dict, Any


class SendMessage(BaseRequest):
    def __init__(self, shop_id: str, user_id: str, channel_name: str = "pinduoduo"):
        super().__init__(shop_id, user_id, channel_name)
        
        # 检查账户信息是否正确加载
        if not hasattr(self, 'account_name'):
            self.logger.error(f"无法在数据库中找到账户: shop_id={shop_id}, user_id={user_id}")
            raise ValueError("找不到指定的账户信息")

    def send_text(self, recipient_uid, message_content):
        """
        发送文本消息
        """
        url = "https://mms.pinduoduo.com/plateau/chat/send_message"
        data = {
            "data": {
                "cmd": "send_message",
                "request_id": self.generate_request_id(),
                "message": {
                    "to": {
                        "role": "user",
                        "uid": recipient_uid
                    },
                    "from": {
                        "role": "mall_cs"
                    },
                    "content": message_content,
                    "msg_id": None,
                    "type": 0,
                    "is_aut": 0,
                    "manual_reply": 1,
                },
            },
            "client": "WEB"
        }

        result = self.post(url, json_data=data)
        if result and result.get("success") == True:
            if result.get("result", {}).get("error_code") == 10002:
                error_msg = result.get('result', {}).get('error')
                self.logger.error(f"发送文本消息失败: {error_msg}")
                return error_msg
            else:
                return result
        else:
            self.logger.error(f"发送文本消息失败: {result}")
            return None

 
        
    def send_image(self, recipient_uid, image_url):
        """
        发送图片消息
        """
        url = "https://mms.pinduoduo.com/plateau/chat/send_message"
        data = {
            "data": {
                "cmd": "send_message",
                "request_id": self.generate_request_id(),
                "message": {
                    "to": {
                        "role": "user",
                        "uid": recipient_uid
                    },
                    "from": {
                        "role": "mall_cs"
                    },
                    "content": image_url,
                    "msg_id": None,
                    "chat_type": "cs",
                    "type": 1,
                    "is_aut": 0,
                    "manual_reply": 1,
                }
            },
            "client": "WEB"
        }

        result = self.post(url, json_data=data)
        self.logger.info(f"[send_image] API 响应: {result}")
        if result and result.get("success") == True:
            if result.get("result", {}).get("error_code") == 10002:
                error_msg = result.get('result', {}).get('error')
                self.logger.error(f"发送图片消息失败: {error_msg}")
                return error_msg
            self.logger.info(f"图片消息发送成功: recipient={recipient_uid}")
            return result
        else:
            self.logger.error(f"发送图片消息失败: {result}")
            return None

    @classmethod
    def _generate_anti_content(cls) -> str:
        """用 Playwright 无头浏览器执行 anti_content.js 生成 token，缓存 5 分钟"""
        import time
        from pathlib import Path
        from utils.logger_loguru import get_logger
        logger = get_logger("SendMessage")

        now = time.time()
        if cls._anti_content_cache and (now - cls._anti_content_ts) < 300:
            logger.info(f"[anti_content] 使用缓存 (剩余 {300 - (now - cls._anti_content_ts):.0f}s)")
            return cls._anti_content_cache

        html_path = Path(__file__).resolve().parents[4] / "generate_anti_content.html"
        logger.info(f"[anti_content] 启动 Playwright 生成: html={html_path}")
        token = ""
        try:
            import asyncio
            from playwright.async_api import async_playwright

            async def _run():
                async with async_playwright() as p:
                    logger.info(f"[anti_content] Playwright 已连接")
                    import sys
                    if getattr(sys, 'frozen', False):
                        root = Path(sys.executable).parent
                    else:
                        root = Path(__file__).resolve().parents[4]
                    browser_dir = root / "browsers"
                    logger.info(f"[anti_content] 查找浏览器: root={root} browser_dir={browser_dir} exists={browser_dir.exists()}")
                    chrome_dirs = list(browser_dir.glob("chromium-*")) if browser_dir.exists() else []
                    logger.info(f"[anti_content] 找到 chromium 目录: {chrome_dirs}")
                    exe = None
                    if chrome_dirs:
                        exe = str(chrome_dirs[0] / "chrome-win64" / "chrome.exe")
                        logger.info(f"[anti_content] 使用 exe: {exe}")

                    if not exe:
                        logger.warning(f"[anti_content] 未找到 chrome.exe，回退到默认 Playwright 浏览器")
                        browser = await p.chromium.launch(headless=True)
                    else:
                        browser = await p.chromium.launch(headless=True, executable_path=exe)
                    logger.info(f"[anti_content] 浏览器已启动")
                    page = await browser.new_page()
                    # 收集控制台日志
                    page.on("console", lambda msg: logger.info(f"[anti_content] console: {msg.text}"))
                    page.on("pageerror", lambda err: logger.error(f"[anti_content] page error: {err}"))
                    await page.goto(f"file:///{html_path.as_posix()}", wait_until="load")
                    # 等一下 JS 执行完
                    await page.wait_for_timeout(1000)
                    token = await page.title()
                    logger.info(f"[anti_content] 页面已加载, title_len={len(token)} title={token[:80] if token else 'EMPTY'}")
                    await browser.close()
                    return token

            token = asyncio.run(_run())
            logger.info(f"[anti_content] 生成完成: len={len(token)}")
        except Exception as e:
            logger.error(f"[anti_content] 生成失败: {e}")

        if token and len(token) > 100:
            cls._anti_content_cache = token
            cls._anti_content_ts = now
            logger.info(f"[anti_content] 缓存已更新 (有效 5min)")
        return cls._anti_content_cache

    _anti_content_cache: str = ""
    _anti_content_ts: float = 0

    def _build_upload_headers(self, host: str = "") -> dict:
        """构建请求头，host 参数仅用于 file.pinduoduo.com 的上传"""
        anti_content = self._generate_anti_content()
        if not anti_content:
            anti_content = self.cookies.get('anti_content') or self.cookies.get('anti-content', '')
        self.logger.info(f"[_build_upload_headers] cookie_keys={list(self.cookies.keys())[:20]} anti_content={'JS_GEN' if anti_content and len(anti_content) > 100 else 'EMPTY'} {anti_content[:20] if anti_content else ''}")
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "anti-content": anti_content,
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://mms.pinduoduo.com",
            "priority": "u=1, i",
            "referer": "https://mms.pinduoduo.com/chat-merchant/index.html",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }

    def pre_upload_image(self) -> dict | None:
        """获取 PDD 图片上传签名。返回 {upload_signature, upload_url, upload_bucket_tag} 或 None"""
        url = "https://mms.pinduoduo.com/plateau/file/pre_upload"
        data = {"chat_type_id": 1, "file_usage": 1}
        headers = self._build_upload_headers()
        self.logger.info(f"[pre_upload] 请求: url={url} data={data} headers_keys={list(headers.keys())}")
        result = self.post(url, json_data=data, headers=headers)
        self.logger.info(f"[pre_upload] 响应: {result}")
        if result and result.get("success") and result.get("result"):
            r = result["result"]
            self.logger.info(f"[pre_upload] 成功: upload_url={r.get('upload_url')} "
                           f"signature_len={len(r.get('upload_signature', ''))}")
            return r
        self.logger.error(f"[pre_upload] 失败: {result}")
        return None

    def upload_image_to_pdd(self, local_path: str) -> str | None:
        """上传本地图片到 PDD CDN，返回公网 URL 或 None"""
        import os
        import base64

        # Step 1: 获取上传签名
        self.logger.info(f"[upload_pdd] Step 1: 获取上传签名...")
        signature_data = self.pre_upload_image()
        if not signature_data:
            return None

        upload_url = signature_data.get("upload_url")
        upload_signature = signature_data.get("upload_signature")
        self.logger.info(f"[upload_pdd] Step 1 完成: upload_url={upload_url}")

        if not upload_url or not upload_signature:
            self.logger.error("[upload_pdd] pre_upload 返回数据不完整")
            return None

        # Step 2: 读图片文件转 base64
        self.logger.info(f"[upload_pdd] Step 2: 读取文件 {local_path}")
        try:
            with open(local_path, "rb") as f:
                raw_bytes = f.read()
            image_base64 = base64.b64encode(raw_bytes).decode("utf-8")
            self.logger.info(f"[upload_pdd] Step 2 完成: file_size={len(raw_bytes)} base64_len={len(image_base64)}")
        except Exception as e:
            self.logger.error(f"[upload_pdd] Step 2 失败: {e}")
            return None

        # Step 3: POST 到 PDD 上传接口（JSON body，base64 图片）
        headers = self._build_upload_headers(host="file.pinduoduo.com")
        headers["content-type"] = "application/json"
        headers["accept"] = "*/*"
        headers["host"] = "file.pinduoduo.com"
        headers["referer"] = "https://mms.pinduoduo.com/"
        headers["sec-fetch-dest"] = "empty"
        headers["sec-fetch-mode"] = "cors"
        headers["sec-fetch-site"] = "same-site"
        # 打印完整 cookie 列表，检查 terminalFinger 是否存在
        all_cookie_keys = {k: v[:30] if isinstance(v, str) else v for k, v in self.cookies.items()}
        self.logger.info(f"[upload_pdd] ALL cookies: {all_cookie_keys}")
        self.logger.info(f"[upload_pdd] Step 3: POST {upload_url} body_keys=[image, upload_signature]")

        import requests
        try:
            resp = requests.post(
                upload_url,
                json={"image": image_base64, "upload_signature": upload_signature},
                headers=headers,
                cookies=self.cookies,
                timeout=30,
            )
            self.logger.info(f"[upload_pdd] Step 3 HTTP: status={resp.status_code}")
            resp_data = resp.json()
            self.logger.info(f"[upload_pdd] Step 3 响应: {resp_data}")
        except Exception as e:
            self.logger.error(f"[upload_pdd] Step 3 失败: {e}")
            return None

        pdd_url = resp_data.get("url")
        if pdd_url:
            filename = os.path.basename(local_path)
            self.logger.info(f"[upload_pdd] 成功: {filename} → {pdd_url}")
            return pdd_url
        self.logger.error(f"[upload_pdd] 响应无 url: {resp_data}")
        return None

    def send_mallGoodsCard(self, recipient_uid, goods_id, biz_type: int = 2):
        """发送商城商品卡片消息"""
        url = "https://mms.pinduoduo.com/plateau/message/send/mallGoodsCard"
        data = {"uid": recipient_uid, "goods_id": goods_id, "biz_type": biz_type}

        anti_content = self.cookies.get('anti_content') or self.cookies.get('anti-content', '')
        self.logger.info(f"[mallGoodsCard] cookie_keys={list(self.cookies.keys())[:15]} "
                        f"anti_content={'PRESENT' if anti_content else 'EMPTY'} "
                        f"anti_content_value={anti_content[:30] if anti_content else ''}")

        headers = self._build_upload_headers()
        headers["referer"] = "https://mms.pinduoduo.com/chat-merchant/index.html"

        self.logger.info(f"[mallGoodsCard] 请求: url={url} goods_id={goods_id} "
                        f"recipient={recipient_uid} biz_type={biz_type}")
        result = self.post(url, json_data=data, headers=headers)
        self.logger.info(f"[mallGoodsCard] 响应: {result}")
        if result:
            if result.get("success"):
                self.logger.info(f"[mallGoodsCard] 成功: goods_id={goods_id}")
            else:
                self.logger.error(f"[mallGoodsCard] 失败: {result}")
            return result


    def getAssignCsList(self):
        """获取分配的客服列表"""
        url = "https://mms.pinduoduo.com/latitude/assign/getAssignCsList"
        data = {"wechatCheck": True}
        self.logger.info(f"[getAssignCsList] 请求: url={url}")
        result = self.post(url, json_data=data)
        self.logger.info(f"[getAssignCsList] 响应: {result}")
        if result and result.get('success'):
            cs_list = result.get('result', {}).get('csList')
            self.logger.info(f"[getAssignCsList] 成功: {len(cs_list) if cs_list else 0} 个客服")
            return cs_list
        else:
            error_msg = result.get('result', {}).get('error') if result else "请求失败"
            self.logger.error(f"[getAssignCsList] 失败: {error_msg}")
            return None

    def move_conversation(self, recipient_uid, cs_uid):
        """转移会话"""
        url = "https://mms.pinduoduo.com/plateau/chat/move_conversation"
        data = {
            "data": {
                "cmd": "move_conversation",
                "request_id": self.generate_request_id(),
                "conversation": {
                    "csid": cs_uid,
                    "uid": recipient_uid,
                    "need_wx": False,
                    "remark": "AI客服自动转接"
                }
            },
            "client": "WEB"
        }
        self.logger.info(f"[move_conversation] 请求: recipient={recipient_uid} cs_uid={cs_uid}")
        result = self.post(url, json_data=data)
        self.logger.info(f"[move_conversation] 响应: {result}")
        if result:
            if result.get("success"):
                self.logger.info(f"[move_conversation] 成功: {recipient_uid} → {cs_uid}")
            else:
                self.logger.error(f"[move_conversation] 失败: {result}")
            return result
