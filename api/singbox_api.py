"""
Singbox管理API端点
提供singbox配置管理和状态查看接口
"""

from fastapi import APIRouter, HTTPException
from scheduler.singbox_scheduler import get_config_info
from api.response import not_found_response

router = APIRouter(prefix="/singbox") 

@router.get("/config.json")
async def get_singbox_config_json():
    """获取singbox配置信息"""
    info = get_config_info()

    if info:
        return info
    else:
        return not_found_response(msg="Error getting config json")

