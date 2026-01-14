"""
IPTV API模块
提供IPTV M3U配置文件的访问接口
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import os

# 创建路由器
router = APIRouter(prefix="/iptv")

# 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
iptv_dir = os.path.join(project_root, 'public', 'iptv')
iptv_path = os.path.join(iptv_dir, 'config.m3u')


@router.get("/config.m3u", response_class=PlainTextResponse)
async def get_iptv_config():
    """
    获取IPTV M3U配置文件内容
    
    返回:
        PlainTextResponse: IPTV M3U配置文件内容
    """
    try:
        if os.path.exists(iptv_path):
            with open(iptv_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # text/x-mpegUR
            return PlainTextResponse(
                content=content,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="config.m3u"'
                }
            )
        else:
            print(f"[IPTV] 配置文件不存在: {iptv_path}")    
    except Exception as e:
        print(f"[IPTV] 获取IPTV配置文件失败: {e}")


