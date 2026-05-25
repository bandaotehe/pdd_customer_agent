from ..base_request import BaseRequest


class GetUserInfo(BaseRequest):
    def __init__(self, cookies=None):

        super().__init__()
        if cookies:
            self.update_cookies(cookies)
    def get_user_info(self):
        url = "https://mms.pinduoduo.com/janus/api/new/userinfo"
        
        result = self.post(url, data="")
        
        if result and result.get("success") == True:
            result_data = result.get('result', {})
            user_id = result_data.get('id')
            user_name = result_data.get('username')
            mall_id = result_data.get('mall_id')
            return user_id, user_name, mall_id
        else:
            error_msg = result.get('errorMsg') if result else "获取用户信息失败"
            self.logger.error(f"获取用户信息失败: {error_msg}")
            return False