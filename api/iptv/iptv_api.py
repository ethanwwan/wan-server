"""
IPTV API模块
提供IPTV M3U配置文件的访问接口
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from .iptv_favorite_utils import fetch_iptv_favorite_config
from .iptv_nas_utils import fetch_iptv_nas_playlist

# 创建路由器
router = APIRouter(prefix="/iptv")

@router.get("/favorite.m3u", response_class=PlainTextResponse)
async def get_iptv_favorite_config():
    """
    获取IPTV收藏 M3U配置文件内容
    
    返回:
        PlainTextResponse: IPTV收藏 M3U配置文件内容
    """

    config_content =  fetch_iptv_favorite_config()

    if config_content:
        return PlainTextResponse(
                content=config_content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="favorite.m3u"'
                }
            )
    else:
            print(f"[IPTV] 请求返回空内容")    
    

@router.get("/playlist.m3u", response_class=PlainTextResponse)
async def get_iptv_playlist():
    """
    获取IPTV NAS M3U配置文件内容
    
    返回:
        PlainTextResponse: IPTV NAS M3U配置文件内容
    """

    content =  fetch_iptv_nas_playlist()

    if content:
        return PlainTextResponse(
                content=content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="playlist.m3u"'
                }
            )
    else:
            print(f"[IPTV] 请求返回空内容")    