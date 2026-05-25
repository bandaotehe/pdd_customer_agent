from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import json

Base = declarative_base()

class Channel(Base):
    """渠道表，存储电商渠道基本信息"""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String(50), unique=True, nullable=False, comment='渠道名称')
    description = Column(String(255), comment='渠道描述')

    # 关联关系 - 一个渠道可以有多个店铺
    shops = relationship('Shop', back_populates='channel', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Channel(channel_name='{self.channel_name}')>"


class Shop(Base):
    """店铺表，存储店铺基本信息"""
    __tablename__ = 'shops'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False)
    shop_id = Column(String(100), nullable=False, comment='店铺ID')
    shop_name = Column(String(100), nullable=False, comment='店铺名称')
    shop_logo = Column(String(255), nullable=True, comment='店铺logo')
    description = Column(String(255), comment='店铺描述')

    # 关联关系 - 多个店铺属于一个渠道，一个店铺可以有多个账号
    channel = relationship('Channel', back_populates='shops')
    accounts = relationship('Account', back_populates='shop', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Shop(shop_id='{self.shop_id}', shop_name='{self.shop_name}', channel='{self.channel.channel_name if self.channel else None}')>"


class Account(Base):
    """账号表，存储店铺账号信息"""
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(Integer, ForeignKey('shops.id'), nullable=False)
    user_id = Column(String(100), nullable=False, comment='用户ID')
    username = Column(String(100), nullable=False, comment='登录用户名')
    password = Column(String(255), nullable=False, comment='登录密码')
    cookies = Column(Text, comment='存储登录cookies信息的JSON字符串')
    status = Column(Integer, default=None, comment='账号状态: None-未验证, 0-休息,1-在线, 3-离线')

    # 关联关系 - 多个账号属于一个店铺
    shop = relationship('Shop', back_populates='accounts')

    def __repr__(self):
        return f"<Account(username='{self.username}', shop='{self.shop.shop_name if self.shop else None}')>"


class Keyword(Base):
    """关键词表，存储关键词信息"""
    __tablename__ = 'keywords'

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(100), nullable=False, comment='关键词')

    def __repr__(self):
        return f"<Keyword(keyword='{self.keyword}')>"


class ProductKnowledge(Base):
    """产品知识表，存储LLM提取的商品详细知识"""
    __tablename__ = 'product_knowledge'

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(Integer, ForeignKey('shops.id', ondelete='CASCADE'), nullable=False, comment='店铺ID')

    __table_args__ = (
        UniqueConstraint('shop_id', 'goods_id', name='uix_product_knowledge_shop_goods'),
    )
    goods_id = Column(Integer, nullable=False, comment='商品ID')
    goods_name = Column(String(255), nullable=False, comment='商品名称')
    price = Column(String(50), nullable=True, comment='价格范围（文本格式）')
    price_min = Column(Integer, nullable=True, comment='最低价（分）')
    price_max = Column(Integer, nullable=True, comment='最高价（分）')
    sold_quantity = Column(Integer, nullable=True, comment='已售数量')
    thumb_url = Column(String(500), nullable=True, comment='商品缩略图URL')
    specifications = Column(Text, nullable=True, comment='规格信息（JSON格式）')
    extracted_content = Column(Text, nullable=True, comment='LLM提取的详细产品知识')
    image_path = Column(String(500), nullable=True, comment='产品图片本地路径')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    last_extracted_at = Column(DateTime, default=datetime.now, comment='上次提取时间')

    # 关联关系
    shop = relationship('Shop', backref='product_knowledge')

    def __repr__(self):
        return f"<ProductKnowledge(goods_id='{self.goods_id}', goods_name='{self.goods_name}')>"


class CustomerServiceKnowledge(Base):
    """客服知识表，存储人工添加的客服话术和规则知识"""
    __tablename__ = 'customer_service_knowledge'

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(Integer, ForeignKey('shops.id', ondelete='CASCADE'), nullable=False, comment='店铺ID')
    title = Column(String(255), nullable=False, comment='知识标题')
    content = Column(Text, nullable=False, comment='知识内容')
    tags = Column(String(255), nullable=True, comment='标签（逗号分隔）')
    enabled = Column(Boolean, default=True, nullable=False, comment='是否启用')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关联关系
    shop = relationship('Shop', backref='customer_service_knowledge')

    def __repr__(self):
        return f"<CustomerServiceKnowledge(title='{self.title}', enabled={self.enabled})>"


class CustomKnowledge(Base):
    """自定义知识表，存储手动输入的知识内容"""
    __tablename__ = 'custom_knowledge'

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(Integer, ForeignKey('shops.id', ondelete='CASCADE'), nullable=False, comment='店铺ID')
    title = Column(String(255), nullable=False, comment='知识标题')
    content = Column(Text, nullable=False, comment='完整原始内容')
    chunk_count = Column(Integer, default=0, comment='分块数量')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    shop = relationship('Shop', backref='custom_knowledge')

    def __repr__(self):
        return f"<CustomKnowledge(title='{self.title}', chunks={self.chunk_count})>"
