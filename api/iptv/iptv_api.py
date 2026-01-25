"""
IPTV API模块
提供IPTV M3U配置文件的访问接口
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from .iptv_utils import fetch_iptv_nas_playlist, fetch_migu_playlist, fetch_ott_playlist, fetch_iptv_favorite_list

# 创建路由器
router = APIRouter(prefix="/iptv", tags=["IPTV"])

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
            print(f"[IPTV] IPTV NAS请求返回空内容")    


@router.get("/migu.m3u", response_class=PlainTextResponse)
async def get_migu_playlist():
    """
    获取Migu M3U配置文件内容
    
    返回:
        PlainTextResponse: Migu M3U配置文件内容
    """

    content =  fetch_migu_playlist()

    if content:
        return PlainTextResponse(
                content=content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="migu.m3u"'
                }
            )
    else:
            print(f"[IPTV] Migu请求返回空内容")    

@router.get("/ott.m3u", response_class=PlainTextResponse)
async def get_ott_playlist():
    """
    获取OTT M3U配置文件内容
    
    返回:
        PlainTextResponse: OTT M3U配置文件内容
    """

    content =  fetch_ott_playlist()

    if content:
        return PlainTextResponse(
                content=content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="ott.m3u"'
                }
            )
    else:
            print(f"[IPTV] OTT请求返回空内容")    
            

@router.get("/favlist.m3u", response_class=PlainTextResponse)
async def get_iptv_favorite_list():
    """
    获取IPTV收藏 M3U配置文件内容
    
    返回:
        PlainTextResponse: IPTV收藏 M3U配置文件内容
    """

    config_content =  fetch_iptv_favorite_list()

    if config_content:
        return PlainTextResponse(
                content=config_content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="favlist.m3u"'
                }
            )
    else:
            print(f"[IPTV] IPTV收藏请求返回空内容")    
    
