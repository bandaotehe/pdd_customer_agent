from ..base_request import BaseRequest


class AccountMonitor(BaseRequest):
    def __init__(self, cookies=None, shop_id=None, user_id=None, channel_name="pinduoduo"):
        # 如果直接传入cookies，同时支持传入账户信息用于自动重新登录
        super().__init__(shop_id=shop_id, user_id=user_id, channel_name=channel_name)
        if cookies:
            self.update_cookies(cookies)
    def set_csstatus(self, status: str):
        url = 'https://mms.pinduoduo.com/plateau/chat/set_csstatus'
        
        data = {
            "data": {
                "cmd": "set_csstatus",
                "status": status
            },
            "client": "WEB"
        }
        
        # 使用基类的post方法
        result = self.post(url, json_data=data)
        
        if result and result.get("success") == True:
            return True
        else:
            error_msg = result.get('errorMsg') if result else "设置状态失败"
            self.logger.error(f"账号 设置状态失败: {error_msg}")
            return False
            

   



