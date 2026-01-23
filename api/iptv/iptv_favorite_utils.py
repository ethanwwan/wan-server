"""
IPTV收藏工具模块
提供IPTV收藏 M3U配置文件的解析、优化和组装功能
"""
import re
from datetime import datetime
import urllib3
import requests

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

def fetch_iptv_favorite_config():
    """
    获取IPTV收藏 M3U配置文件内容
    """

    print(f"[IPTV] 开始读取收藏配置，时间: {datetime.now().isoformat()}")
    
    try:
        # 发送请求
        response = requests.get(favorite_url, headers=favorite_headers, verify=False, timeout=30)
        config_content = response.text.strip()

        if config_content:
            
            print(f"[IPTV] 开始优化收藏配置，时间: {datetime.now().isoformat()}")
            # 解析并优化配置
            filtered_channels = parse_and_filter_favorite_channels(config_content, favorite_channels)
            
            # 按URL优先级排序
            sorted_channels = sort_channels_by_url_priority(filtered_channels)

            # 重新组装成M3U格式
            optimized_config = assemble_m3u_config(sorted_channels)

            print(f"[IPTV] 收藏配置读取完成，时间: {datetime.now().isoformat()}")
            
            return optimized_config
            
        else:
            print(f"[IPTV] 请求返回空内容")
        
    except Exception as e:
        print(f"[IPTV] 收藏配置读取失败: {e}")

def parse_and_filter_favorite_channels(config_content, favorite_channels):
    """
    解析M3U配置文件并过滤出收藏的频道
    
    Args:
        config_content: M3U配置文件内容
        favorite_channels: 收藏频道列表
    
    返回:
        list: 过滤后的频道信息列表
    """
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
                
                # 遍历favorite_channels，判断favorite_channel是否在channel_name中
                for favorite_channel in favorite_channels:
                    if favorite_channel.upper() in channel_name.upper():
                        # 添加频道信息
                        channels.append({
                            "name": channel_name,
                            "tvg_name": tvg_name.upper() if tvg_name else None,
                            "tvg_logo": tvg_logo,
                            "group_title": group_title,
                            "url": url_line.strip()
                        })

    return channels



def sort_channels_by_url_priority(channels):
    """
    按URL优先级排序频道
    
    排序规则：
    1. 第一遍排序：按照group-title字段中的，央视，卫视，地方，其他分类
    2. 第二遍排序：包含live.ottiptv.cc的URL优先。包含mgtv.ottiptv.cc的URL次之。其他URL最后。
    3. 相同优先级按URL字母顺序排序
    
    Args:
        channels: 频道信息列表
    
    返回:
        list: 排序后的频道信息列表
    """
    def get_sort_key(channel):
        """
        生成排序键
        
        Args:
            channel: 频道信息字典
        
        返回:
            tuple: 排序键元组
        """
        # 1. 按group-title分类排序
        group_title = channel.get('group_title', '').strip()
        group_priority = {
            '央视': 0,
            '卫视': 1,
            '地方': 2
        }
        # 默认优先级为3（其他分类）
        group_score = group_priority.get(group_title, 3)
        
        # 2. 按域名优先级排序
        url = channel.get('url', '')
        domain_priorities = ['live.ottiptv.cc', 'mgtv.ottiptv.cc']
        domain_score = len(domain_priorities)
        for i, domain in enumerate(domain_priorities):
            if domain in url:
                domain_score = i
                break
 
        return (group_score, domain_score)
    
    return sorted(channels, key=get_sort_key)

def assemble_m3u_config(channels):
    """
    重新组装成M3U格式配置
    
    Args:
        channels: 频道信息列表
    
    返回:
        str: M3U格式配置内容
    """
    config = "#EXTM3U x-tvg-url=\"https://11.112114.xyz/pp.xml\"\n"
    
    for channel in channels:
        # 构建EXTINF行
        extinf_parts = ["#EXTINF:-1"]
        
        if channel['tvg_name']:
            extinf_parts.append(f"tvg-name=\"{channel['tvg_name']}\"")
        
        if channel['tvg_logo']:
            extinf_parts.append(f"tvg-logo=\"{channel['tvg_logo']}\"")
        
        if channel['group_title']:
            extinf_parts.append(f"group-title=\"{channel['group_title']}\"")
        
        extinf_line = " ".join(extinf_parts) + f",{channel['name']}"
        config += f"{extinf_line}\n"
        config += f"{channel['url']}\n"
    
    return config

