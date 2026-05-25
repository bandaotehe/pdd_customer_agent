from ..base_request import BaseRequest


class ProductManager(BaseRequest):
    """
    拼多多商品管理API
    提供商品列表查询和商品详情获取功能
    """

    def __init__(self, shop_id: str = None, user_id: str = None, cookies=None):
        """
        初始化商品管理器

        Args:
            shop_id: 店铺ID，用于从数据库获取cookies
            user_id: 用户ID，用于从数据库获取cookies
            cookies: 登录cookies，如果直接传入则不需要从数据库获取
        """
        super().__init__(shop_id=shop_id, user_id=user_id)
        if cookies:
            self.update_cookies(cookies)

    def get_product_list(self, page=1, size=10):
        """
        获取店铺商品列表

        Args:
            page (int): 页码，默认1
            size (int): 每页数量，默认10

        Returns:
            dict: 商品列表结果，格式如下：
                {
                    "success": True/False,
                    "products": [
                        {
                            "goods_id": int,
                            "goods_name": str,
                            "thumb_url": str,       # 商品缩略图
                            "price": float,         # 价格
                            "sold_quantity": int,   # 已售数量
                            "goods_type": int,      # 商品类型
                            "tag": str,             # 商品标签
                        },
                        ...
                    ],
                    "total": int,  # 总数量
                    "page": int,   # 当前页码
                    "error_msg": str  # 仅在失败时包含
                }
        """
        # 构建请求URL
        url = "https://mms.pinduoduo.com/latitude/goods/recommendGoods"

        # 构建请求数据
        data = {
            "uid": "",
            "pageNum": page,
            "pageSize": size
        }

        # 构建请求头（与浏览器请求完全一致）
        # anti-content 从 cookies 中获取（由后端动态生成）
        anti_content = self.cookies.get('anti_content') or self.cookies.get('anti-content', '')
        headers = {
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
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }

        # 发起请求
        result = self.post(url, json_data=data, headers=headers)

        if result and result.get("success") == True:
            # 解析商品列表
            products_data = self._parse_product_list(result)
            return {
                "success": True,
                "products": products_data.get("products", []),
                "total": products_data.get("total", 0),
                "page": page
            }
        else:
            error_msg = result.get('errorMsg') if result else "获取商品列表失败"
            self.logger.error(f"获取商品列表失败: {error_msg}")
            return {
                "success": False,
                "error_msg": error_msg,
                "products": [],
                "total": 0,
                "page": page
            }

    def get_product_detail(self, goods_id):
        """
        根据商品ID获取商品详细信息

        Args:
            goods_id (int): 商品ID

        Returns:
            dict: 商品详情结果，格式如下：
                {
                    "success": True/False,
                    "product_info": {
                        "goods_id": int,
                        "goods_name": str,
                        "specifications": str/dict,
                        "price": float,
                        "description": str,
                        # TODO: 根据实际API响应添加更多字段
                    },
                    "error_msg": str  # 仅在失败时包含
                }
        """
        if not goods_id:
            self.logger.error("商品ID不能为空")
            return {"success": False, "error_msg": "商品ID不能为空"}

        # 构建请求URL
        url = "https://mms.pinduoduo.com/glide/v2/mms/query/commit/on_shop/detail"

        # 构建请求数据
        data = {"goods_id": goods_id}

        # 构建请求头，添加anti-content
        anti_content = self.cookies.get('anti_content') or self.cookies.get('anti-content', '')
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "anti-content": anti_content,
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://mms.pinduoduo.com",
            "referer": "https://mms.pinduoduo.com/chat-merchant/index.html",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }

        # 发起请求
        result = self.post(url, json_data=data, headers=headers)

        if result and result.get("success") == True:
            # 解析商品详细信息
            product_info = self._parse_product_detail(result)
            return {
                "success": True,
                "product_info": product_info
            }
        else:
            error_msg = result.get('errorMsg') if result else "获取商品详情失败"
            self.logger.error(f"获取商品详情失败 (goods_id={goods_id}): {error_msg}")
            return {
                "success": False,
                "error_msg": error_msg
            }

    def _parse_product_list(self, response_data):
        """
        解析商品列表响应数据

        Args:
            response_data (dict): API响应数据

        Returns:
            dict: 解析后的商品列表数据
        """
        try:
            result_data = response_data.get('result', {})
            # 拼多多API商品列表在 onSaleGoods 字段中
            goods_list = result_data.get('onSaleGoods', [])

            products = []
            for goods in goods_list:
                # 价格：使用区间价格，最低价-最高价
                min_price = goods.get('minOnSaleGroupPrice')
                max_price = goods.get('maxOnSaleGroupPrice')
                if min_price and max_price and min_price != max_price:
                    price_str = f"{min_price/100:.2f}-{max_price/100:.2f}"
                elif min_price:
                    price_str = f"{min_price/100:.2f}"
                else:
                    price_str = None

                # 提取商品标签
                goods_tag = goods.get('goodsTag', {})
                marketing_tags = goods_tag.get('marketingTags', [])
                tag_str = ', '.join(marketing_tags) if marketing_tags else ''

                product = {
                    "goods_id": goods.get('goodsId'),
                    "goods_name": goods.get('goodsName', ''),
                    "thumb_url": goods.get('thumbUrl', ''),
                    "price": price_str,
                    "price_min": min_price,
                    "price_max": max_price,
                    "sold_quantity": goods.get('soldQuantity', 0),
                    "sold_quantity_30d": goods.get('soldQuantity30d', 0),
                    "quantity": goods.get('quantity', 0),  # 库存
                    "goods_type": goods.get('goodsType', ''),
                    "is_spike": goods.get('isSpike', False),  # 是否秒杀
                    "support_customize": goods.get('supportCustomize', False),  # 是否支持定制
                    "goods_url": goods.get('goodsUrl', ''),  # 商品链接
                    "tag": tag_str,
                }
                products.append(product)

            return {
                "products": products,
                "total": result_data.get('total', len(products))
            }

        except Exception as e:
            self.logger.error(f"解析商品列表失败: {str(e)}")
            return {
                "products": [],
                "total": 0
            }

    def _parse_product_detail(self, response_data):
        """
        解析商品详情响应数据

        Args:
            response_data (dict): API响应数据

        Returns:
            dict: 解析后的商品详情
        """
        try:
            result_data = response_data.get('result', {})

            # 提取规格信息
            specifications = []
            skus = result_data.get('skus', [])

            if skus:
                for sku in skus:
                    # 获取规格组合信息
                    specs = sku.get('spec', [])
                    if specs:
                        spec_text = []
                        for spec_item in specs:
                            parent_name = spec_item.get('parent_name', '')
                            spec_name = spec_item.get('spec_name', '')
                            if parent_name and spec_name:
                                spec_text.append(f"{parent_name}: {spec_name}")
                            elif spec_name:
                                spec_text.append(spec_name)

                        if spec_text:
                            specifications.append(" | ".join(spec_text))

            # 提取分类信息作为规格补充
            cats = result_data.get('cats', [])
            if cats and isinstance(cats, list):
                # 过滤掉空值并组合分类信息
                valid_cats = [cat for cat in cats if cat]
                if valid_cats:
                    specifications.append(f"商品分类: {' > '.join(valid_cats)}")

            product_info = {
                "goods_id": result_data.get('goods_id'),
                "goods_name": result_data.get('goods_name', ''),
                "specifications": specifications[:20]  # 最多显示20个规格信息
            }

            return product_info

        except Exception as e:
            self.logger.error(f"解析商品详情失败: {str(e)}")
            return {
                "goods_id": None,
                "goods_name": "解析失败",
                "specifications": []
            }