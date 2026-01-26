"""
IPTV NAS M3U配置文件工具模块
提供获取IPTV NAS M3U配置文件内容的功能
"""

import os
import requests
import re

# 从环境变量读取配置，如果没有设置则使用默认值
PLAYLIST_URL = os.getenv("IPTV_PLAYLIST_URL", "")
MIGU_URL = os.getenv("IPTV_MIGU_URL", "")
OTT_URL = os.getenv("IPTV_OTT_URL", "")

# 从环境变量读取喜欢的频道列表，格式为逗号分隔的频道名称
FAVORITE_CHANNELS = os.environ.get("FAVORITE_CHANNELS", "CCTV1,CCTV3,江苏卫视").split(",")  


def fetch_iptv_nas_playlist():
    """
    获取IPTV NAS M3U配置文件内容
    """
    return requests.get(PLAYLIST_URL, verify=False, timeout=20).text.strip()

def fetch_migu_playlist():
    """
    获取Migu M3U配置文件内容
    """
    return requests.get(MIGU_URL, verify=False, timeout=20).text.strip()

def fetch_ott_playlist():
    """
    获取OTT M3U配置文件内容
    """
    return requests.get(OTT_URL, verify=False, timeout=20).text.strip()


def parse_m3u_content(content, source_name):
    """
    解析M3U内容，提取频道信息
    
    Args:
        content: M3U文件内容
        source_name: 数据源名称
    
    Returns:
        list: 频道信息列表，每个元素包含(extinf_line, url_line, channel_name)
    """
    channels = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF'):
            # 提取频道名称
            channel_name = lines[i].split(',')[-1].strip()
            
            # 检查是否有对应的URL行
            if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                channels.append((lines[i], lines[i + 1], channel_name))
                print(f"[{source_name}] 发现频道: {channel_name}")
        i += 1
    
    print(f"[{source_name}] 解析完成，共 {len(channels)} 个频道")
    return channels


def fetch_iptv_favorite_list():
    """
    获取IPTV收藏 M3U配置文件内容
    从所有数据源统一筛选出喜欢的频道
    
    Returns:
        str: 只包含喜欢频道的M3U配置文件内容
    """
    try:
        print("[IPTV] 开始获取收藏频道列表")
        print(f"[IPTV] 喜欢的频道列表: {FAVORITE_CHANNELS}")
        
        # 获取所有数据源的M3U内容
        sources = [
            ("NAS", fetch_iptv_nas_playlist()),
            ("Migu", fetch_migu_playlist()),
            ("OTT", fetch_ott_playlist())
        ]
        
        # 解析所有数据源的频道
        all_channels = []
        for source_name, content in sources:
            if content:
                channels = parse_m3u_content(content, source_name)
                all_channels.extend(channels)
            else:
                print(f"[{source_name}] 数据源返回空内容") 
        
        # 筛选喜欢的频道
        favorite_channels = []
        channel_count = 0
        
        for extinf_line, url_line, channel_name in all_channels:
            # 检查是否匹配喜欢的频道
            matched = False
            
            for fav_channel in FAVORITE_CHANNELS:
                if fav_channel:
                    # 检查是否完全匹配或者以喜欢频道名称开头且后面跟着非字母数字字符或结束
                    pattern = r'^' + re.escape(fav_channel.upper()) + r'($|[^a-zA-Z0-9])'
                    if re.search(pattern, channel_name.upper()):
                        matched = True
                        break
            
            if matched:
                favorite_channels.append((extinf_line, url_line))
                channel_count += 1
                print(f"[IPTV] 添加收藏频道: {channel_name}")
        
        # 生成M3U文件
        m3u_lines = []
        
        # 添加文件头
        m3u_lines.append('#EXTM3U x-tvg-url="http://192.168.1.12:8015/migu/playback.xml" catchup="append" catchup-source="?playbackbegin=${(b)yyyyMMddHHmmss}&playbackend=${(e)yyyyMMddHHmmss}"')
        
        # 添加收藏频道
        for extinf_line, url_line in favorite_channels:
            # 提取频道名称以确定分组
            channel_name = extinf_line.split(',')[-1].strip()
            
            # 确定分组
            if 'CCTV' in channel_name.upper():
                group_title = '央视频道'
            elif '卫视' in channel_name.upper():
                group_title = '卫视频道'
            else:
                group_title = '地方频道'
            
            # 添加或修改group-title字段
            if 'group-title=' in extinf_line:
                # 替换已存在的group-title值
                extinf_line = re.sub(r'group-title=\"[^"]*\"', f'group-title="{group_title}"', extinf_line)
            else:
                # 添加新的group-title字段
                if extinf_line.endswith('"'):
                    # 如果行尾有引号，在引号前添加
                    extinf_line = extinf_line[:-1] + f' group-title="{group_title}"' + extinf_line[-1]
                else:
                    # 如果行尾没有引号，直接添加
                    extinf_line = extinf_line + f' group-title="{group_title}"'
            
            m3u_lines.append(extinf_line)
            m3u_lines.append(url_line)
        
        # 生成最终内容
        result = '\n'.join(m3u_lines)
        print(f"[IPTV] 收藏频道列表生成完成，共 {channel_count} 个频道")
        
        return result
        
    except Exception as e:
        print(f"[IPTV] 生成收藏频道列表失败: {str(e)}")
        # 返回空内容，避免影响服务
        return '#EXTM3U\n'  
