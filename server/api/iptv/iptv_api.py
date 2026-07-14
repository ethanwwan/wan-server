import os
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from ..base.response import not_found_response

router = APIRouter(prefix="/iptv", tags=["IPTV"])

IPTV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'output', 'iptv')


@router.get("/playlist.m3u", response_class=PlainTextResponse)
async def get_playlist():
    file_path = os.path.join(IPTV_DIR, 'playlist.m3u')
    if not os.path.exists(file_path):
        return not_found_response(msg="playlist.m3u 不存在")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return PlainTextResponse(
            content=content,
            media_type="text/x-mpegURL",
            headers={"Content-Disposition": 'inline; filename="playlist.m3u"'}
        )
    except Exception as e:
        return not_found_response(msg=f"读取 playlist.m3u 失败：{str(e)}")


@router.get("/{file_name:path}")
async def get_iptv_file(file_name: str):
    file_path = os.path.join(IPTV_DIR, file_name)
    if not os.path.exists(file_path):
        return not_found_response(msg=f"IPTV 文件 {file_name} 不存在")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return PlainTextResponse(
            content=content,
            media_type="text/x-mpegURL",
            headers={"Content-Disposition": 'inline; filename="' + file_name + '"'}
        )
    except Exception as e:
        return not_found_response(msg=f"读取 IPTV 文件 {file_name} 失败：{str(e)}")
