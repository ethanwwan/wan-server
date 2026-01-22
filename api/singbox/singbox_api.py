"""
Singbox管理API端点
提供singbox配置管理和状态查看接口
"""

from fastapi import APIRouter
from scheduler.singbox_scheduler import get_config_json
from api.base.response import not_found_response

router = APIRouter(prefix="/singbox") 

@router.get("/config.json")
async def get_singbox_latest_config():
    """获取singbox配置信息"""
    data = get_config_json(True)

    if data:
        return data
    else:
        return not_found_response(msg="获取配置失败")

@router.get("/config_old.json")
async def get_singbox_old_config():
    """获取singbox旧配置信息"""
    data = get_config_json(False)

    if data:
        return data
    else:
        return not_found_response(msg="获取旧配置失败")