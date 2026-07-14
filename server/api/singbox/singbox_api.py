import os
from fastapi import APIRouter
from fastapi.responses import FileResponse
from ..base.response import not_found_response

router = APIRouter(prefix="/singbox", tags=["SingBox"])

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'output', 'singbox'
)


@router.get("/proxy.json")
async def get_proxy():
    file_path = os.path.join(OUTPUT_DIR, 'proxy.json')
    if not os.path.exists(file_path):
        return not_found_response(msg="proxy.json 不存在")
    try:
        return FileResponse(file_path, media_type="application/json")
    except Exception as e:
        return not_found_response(msg=f"读取 proxy.json 失败：{str(e)}")


@router.get("/proxy_old.json")
async def get_proxy_old():
    file_path = os.path.join(OUTPUT_DIR, 'proxy_old.json')
    if not os.path.exists(file_path):
        return not_found_response(msg="proxy_old.json 不存在")
    try:
        return FileResponse(file_path, media_type="application/json")
    except Exception as e:
        return not_found_response(msg=f"读取 proxy_old.json 失败：{str(e)}")
