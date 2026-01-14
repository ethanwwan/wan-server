"""
API路由管理器
统一管理和组织所有API路由
"""

from fastapi import APIRouter
from api.common import router as common_router

api_router = APIRouter(prefix="/v1")  # 所有业务路由统一在此前缀下
api_router.include_router(common_router)
