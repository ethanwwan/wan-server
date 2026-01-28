"""
IPTV NAS M3U配置文件工具模块
提供获取IPTV NAS M3U配置文件内容的功能
"""

import os
import re

# 从环境变量读取喜欢的频道列表，格式为逗号分隔的频道名称
FAVORITE_CHANNELS = os.getenv("FAVORITE_CHANNELS", "CCTV1,CCTV3,江苏卫视,嵊州").split(",")  

# IPTV配置目录
IPTV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'public', 'iptv')

# 自动扫描IPTV配置目录，获取所有M3U文件
def get_iptv_m3u_file_names():
    """
    扫描IPTV配置目录，获取所有M3U文件
    
    Returns:
        list: IPTV配置 M3U文件列表
    """
    m3u_file_names = []
    if os.path.exists(IPTV_DIR):
        for file_name in os.listdir(IPTV_DIR):
            if file_name.endswith('.m3u'):
                # 排除favlist.m3u文件
                if file_name == "favlist.m3u":
                    continue
                m3u_file_names.append(file_name)
    return m3u_file_names


def parse_iptv_m3u_content(content, source_name):
    """
    解析IPTV M3U3U内容，提取频道信息
    
    Args:
        content: IPTV M3U文件内容   
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

# 按照url_line中包含migu,ottiptv,其他来排序
def get_sort_priority(url_line):
    """获取排序优先级，数字越小优先级越高"""
    url_lower = url_line.lower()
    if 'migu' in url_lower:
        return 0
    elif 'ottiptv' in url_lower:
        return 1
    else:
        return 2

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
        m3u_file_names = get_iptv_m3u_file_names()
        # 根据m3u_file_names读取所有文件内容
        all_channels = []
        for file_name in m3u_file_names:
            file_path = os.path.join(IPTV_DIR, file_name)
            source_name = file_name.split(".")[0]
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if content:
                channels = parse_iptv_m3u_content(content, source_name)
                all_channels.extend(channels)
            else:
                print(f"[{source_name}] 数据源返回空内容") 

        # 筛选喜欢的频道
        favorite_channels = []
        channel_count = 0
        
        for extinf_line, url_line, channel_name in all_channels:

            if "tvg-name" not in extinf_line:
                continue

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
        
        favorite_channels.sort(key=lambda x: get_sort_priority(x[1]))

        # 生成M3U文件
        m3u_lines = []
        
        # 添加文件头
        m3u_lines.append('#EXTM3U x-tvg-url="http://192.168.1.12:8015/migu/playback.xml" catchup="append" catchup-source="?playbackbegin=${(b)yyyyMMddHHmmss}&playbackend=${(e)yyyyMMddHHmmss}"')
        
        # 添加收藏频道
        for extinf_line, url_line in favorite_channels:
            # 提取频道名称以确定分组
            channel_name = extinf_line.split(',')[-1].strip()
            new_channel_name = channel_name.replace('-MCP', '').upper()
    
            # 确定分组
            if 'CCTV' in new_channel_name:
                group_title = '央视频道'
                # 去掉频道名称中的中文字符
                new_channel_name = re.sub(r'[\u4e00-\u9fff]', '', new_channel_name)
            elif '卫视' in new_channel_name:
                group_title = '卫视频道'
            else:
                group_title = '地方频道'
            
            # 替换extinf_line中的channel_name字段为new_channel_name
            extinf_line = extinf_line.replace(channel_name, new_channel_name)

            # 添加或修改group-title字段
            if 'group-title=' in extinf_line:
                # 替换已存在的group-title值
                extinf_line = re.sub(r'group-title=\"[^\"]*\"', f'group-title="{group_title}"', extinf_line)
            else:
                # 添加新的group-title字段
                # 找到逗号位置，在逗号前添加group-title
                comma_index = extinf_line.find(',')
                if comma_index != -1:
                    # 在逗号前插入group-title
                    extinf_line = extinf_line[:comma_index] + f' group-title="{group_title}"' + extinf_line[comma_index:]
                else:
                    # 如果没有逗号（异常情况），保持原样
                    pass
            
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
