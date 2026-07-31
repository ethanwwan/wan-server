"""
TVBox API - 提供 TVBox 配置文件下载
"""
import os
from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..base.response import not_found_response
from server.utils.file_resolver import get_output_file

router = APIRouter(prefix="/tvbox", tags=["TVBox"])

TVBOX_FILE = get_output_file('tvbox', 'config.json')


@router.get("/config.json")
async def get_tvbox():
    if not os.path.exists(TVBOX_FILE):
        return not_found_response(msg="config.json 不存在")
    try:
        return FileResponse(TVBOX_FILE, media_type="application/json")
    except Exception as e:
        return not_found_response(msg=f"读取 config.json 失败：{str(e)}")