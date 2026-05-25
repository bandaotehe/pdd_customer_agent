from ..base_request import BaseRequest


class GetShopInfo(BaseRequest):
    def __init__(self, cookies=None):
        # 如果直接传入cookies，不需要从数据库获取
        super().__init__()
        if cookies:
            self.update_cookies(cookies)
    
    def get_shop_info(self):
        url = "https://mms.pinduoduo.com/earth/api/merchant/queryMerchantInfoByMallId"

        result = self.post(url, json_data={})
        
        if result and result.get("success") == True:
            result_data = result.get('result', {})
            shop_id = result_data.get('mallId')
            shop_name = result_data.get('mallName')
            mallLogo = result_data.get('mallLogo')
            return shop_id, shop_name, mallLogo
        else:
            error_msg = result.get('errorMsg') if result else "获取店铺信息失败"
            self.logger.error(f"获取店铺信息失败: {error_msg}")
            return False