"""
IPTV API模块
提供IPTV M3U配置文件的访问接口
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import os
import re
from datetime import datetime
import urllib3
import requests
from favorite_iptv_utils import parse_and_optimize_iptv_favorite_config, assemble_m3u_config, sort_channels_by_url_priority

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# IPTV M3U URL
favorite_url = "https://live.ottiptv.cc/iptv.m3u?userid=7755950497&sign=90e88816ddcbc02a0041a59a221549ca7511afc47ba095012e074d31e05bad1c33aa52fc0b9e6fd4af5293f73fbea2006e530440fa917bdff9624c924e7e6583c0a71e0c735ca2&auth_token=17b0d6712a2beb7e9bfea802dc9d33a3"

favorite_channels = ["CCTV3","江苏卫视"]

# 设置请求头
favorite_headers = {
    "User-Agent": "okHttp/Mod-1.5.0.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

# 创建路由器
router = APIRouter(prefix="/iptv")

@router.get("/favorite.m3u", response_class=PlainTextResponse)
async def get_iptv_favorite_config():
    """
    获取IPTV收藏 M3U配置文件内容
    
    返回:
        PlainTextResponse: IPTV收藏 M3U配置文件内容
    """

    print(f"[IPTV] 开始读取收藏配置，时间: {datetime.now().isoformat()}")
    
    try:

        # 发送请求
        response = requests.get(favorite_url, headers=favorite_headers, verify=False, timeout=30)
        config_content = response.text.strip()

        if config_content:
            
            print(f"[IPTV] 开始优化收藏配置，时间: {datetime.now().isoformat()}")
            # 解析并优化配置
        
            channels = []
            lines = config_content.splitlines()
            
            # 解析频道信息
            for i in range(len(lines)):
                if lines[i].startswith("#EXTINF") and i + 1 < len(lines):
                    # 解析#EXTINF行
                    extinf_line = lines[i]
                    url_line = lines[i+1]
                    
                    # 提取频道名称（如cctv1-MCP）
                    # 格式示例: #EXTINF:-1 tvg-name="cctv1" tvg-logo="..." group-title="央视",cctv1-MCP
                    channel_name_match = re.search(r',([^,]+)$', extinf_line)
                    if channel_name_match:
                        channel_name = channel_name_match.group(1).strip()
                        
                        # 提取其他信息
                        tvg_name_match = re.search(r'tvg-name="([^"]+)"', extinf_line)
                        tvg_name = tvg_name_match.group(1) if tvg_name_match else None
                        
                        tvg_logo_match = re.search(r'tvg-logo="([^"]+)"', extinf_line)
                        tvg_logo = tvg_logo_match.group(1) if tvg_logo_match else None
                        
                        group_title_match = re.search(r'group-title="([^"]+)"', extinf_line)
                        group_title = group_title_match.group(1) if group_title_match else None
                        
                        # 添加频道信息
                        channels.append({
                            "name": channel_name,
                            "tvg_name": tvg_name.upper(),
                            "tvg_logo": tvg_logo,
                            "group_title": group_title,
                            "url": url_line.strip()
                        })

            # 过滤收藏频道
            filtered_channels = [channel for channel in channels if channel['name'] in favorite_channels]
            
            # 按URL优先级排序
            sorted_channels = sort_channels_by_url_priority(filtered_channels)

            # 重新组装成M3U格式
            optimized_config = assemble_m3u_config(sorted_channels)

            print(f"[IPTV] 收藏配置读取完成，时间: {datetime.now().isoformat()}")
            
            return PlainTextResponse(
                content=optimized_config,
                media_type="text/x-mpegURL",
                headers={
                    "Content-Disposition": 'inline; filename="favorite.m3u"'
                }
            )
            
        else:
            print(f"[IPTV] 请求返回空内容")
        
    except Exception as e:
        print(f"[IPTV] 收藏配置读取失败: {e}")



