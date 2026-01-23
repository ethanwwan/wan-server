"""
API路由管理器
统一管理和组织所有API路由
"""

from fastapi import APIRouter
from api.common.common_api import router as common_router
from api.singbox.singbox_api import router as singbox_router
from api.iptv.iptv_api import router as iptv_router

 # 所有业务路由统一在此前缀下
api_router = APIRouter(prefix="/api") 
api_router.include_router(common_router)
api_router.include_router(singbox_router)
api_router.include_router(iptv_router)
