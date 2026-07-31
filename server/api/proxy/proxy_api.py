"""
Proxy API - 提供 sing-box / Clash 配置文件下载
"""
import os
from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..base.response import not_found_response
from server.utils.file_resolver import get_output_file

router = APIRouter(prefix="/proxy", tags=["Proxy"])


@router.get("/singbox.json")
async def get_singbox():
    file_path = get_output_file('proxy', 'singbox.json')
    if not os.path.exists(file_path):
        return not_found_response(msg="singbox.json 不存在")
    try:
        return FileResponse(file_path, media_type="application/json")
    except Exception as e:
        return not_found_response(msg=f"读取 singbox.json 失败：{str(e)}")


@router.get("/singbox_old.json")
async def get_singbox_old():
    file_path = get_output_file('proxy', 'singbox_old.json')
    if not os.path.exists(file_path):
        return not_found_response(msg="singbox_old.json 不存在")
    try:
        return FileResponse(file_path, media_type="application/json")
    except Exception as e:
        return not_found_response(msg=f"读取 singbox_old.json 失败：{str(e)}")


@router.get("/clash.yaml")
async def get_clash():
    file_path = get_output_file('proxy', 'clash.yaml')
    if not os.path.exists(file_path):
        return not_found_response(msg="clash.yaml 不存在")
    try:
        return FileResponse(
            file_path,
            media_type="application/x-yaml",
            headers={"Content-Disposition": "inline; filename=clash.yaml"}
        )
    except Exception as e:
        return not_found_response(msg=f"读取 clash.yaml 失败：{str(e)}")