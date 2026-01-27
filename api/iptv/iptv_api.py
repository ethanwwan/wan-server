"""
IPTV API模块
提供IPTV M3U配置文件的访问接口
"""

import os
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from .iptv_utils import fetch_iptv_favorite_list,IPTV_DIR
from api.base.response import not_found_response


# 创建路由器
router = APIRouter(prefix="/iptv", tags=["IPTV"])

# IPTV文件读取路由
@router.get("/iptv/{file_name:path}")
async def get_iptv_file(file_name: str):
    """获取IPTV M3U文件"""
    # 检查文件是否存在
    file_path = os.path.join(IPTV_DIR, file_name)
    
    if not os.path.exists(file_path):
        return not_found_response(msg=f"IPTV文件 {file_name} 不存在")
    
    # 读取并返回文件内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return PlainTextResponse(content=content, media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="' + file_name + '"'
                }
            )
    except Exception as e:
        return not_found_response(msg=f"读取IPTV文件 {file_name} 失败: {str(e)}")

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
    
