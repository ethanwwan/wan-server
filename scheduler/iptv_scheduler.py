"""
IPTV配置定时更新模块
负责每8小时自动更新IPTV M3U配置文件
"""

import requests
import os
import re
from datetime import datetime
import urllib3

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 写入本地 config.m3u，使用 UTF-8 编码，保存到项目根目录下的public/iptv目录
# 项目根目录是包含main.py的目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
iptv_dir = os.path.join(project_root, 'public', 'iptv')
iptv_path = os.path.join(iptv_dir, 'config.m3u')

# IPTV M3U URL
iptv_url = "https://live.ottiptv.cc/iptv.m3u?userid=7755950497&sign=90e88816ddcbc02a0041a59a221549ca7511afc47ba095012e074d31e05bad1c33aa52fc0b9e6fd4af5293f73fbea2006e530440fa917bdff9624c924e7e6583c0a71e0c735ca2&auth_token=17b0d6712a2beb7e9bfea802dc9d33a3"


def iptv_scheduler():
    """
    每8小时更新一次IPTV配置
    
    功能：
    - 从远程URL下载最新IPTV M3U内容
    - 解析并优化配置内容
    - 保存到本地配置文件
    """
    print(f"[IPTV] 开始更新配置，时间: {datetime.now().isoformat()}")
    
    try:
        # 设置请求头
        headers = {
            "User-Agent": "okHttp/Mod-1.5.0.0",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        # 发送请求
        response = requests.get(iptv_url, headers=headers, verify=False, timeout=30)
        response.raise_for_status()  # 检查请求是否成功

        config_content = response.text.strip()

        if config_content:
            # 确保public/iptv目录存在
            os.makedirs(iptv_dir, exist_ok=True)

            # 解析并优化配置
            optimized_config = parse_and_optimize_iptv_config(config_content)

            # 写入M3U文件
            with open(iptv_path, 'w', encoding='utf-8') as f:
                f.write(optimized_config)
            
            print(f"[IPTV] 配置更新成功，文件已保存到: {iptv_path}")
        else:
            print(f"[IPTV] 请求返回空内容")
        
        print(f"[IPTV] 配置更新完成，时间: {datetime.now().isoformat()}")
        
    except Exception as e:
        print(f"[IPTV] 配置更新失败: {e}")

def get_iptv_config():
    """
    获取当前IPTV配置内容
    
    返回:
        str: IPTV M3U配置内容，如果文件不存在或读取失败则返回空字符串
    """
    try:
        if os.path.exists(iptv_path):
            with open(iptv_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"[IPTV] 获取配置信息错误: {e}")
    return ""


def parse_and_optimize_iptv_config(config_content):
    """
    解析并优化IPTV M3U配置文件
    
    Args:
        config_content: M3U配置文件内容
    
    返回:
        str: 优化后的M3U配置内容
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
                
                # 添加频道信息
                channels.append({
                    "name": channel_name,
                    "tvg_name": tvg_name.upper(),
                    "tvg_logo": tvg_logo,
                    "group_title": group_title,
                    "url": url_line.strip()
                })

    # 处理频道名称
    processed_channels = process_channel_names(channels)
    
    # 过滤测试频道
    filtered_channels = [channel for channel in processed_channels if '测试' not in channel['name']]
    
    # 按URL优先级排序
    sorted_channels = sort_channels_by_url_priority(filtered_channels)
    
    # 重新组装成M3U格式
    return assemble_m3u_config(sorted_channels)


def process_channel_names(channels):
    """
    处理频道名称，优化命名
    
    Args:
        channels: 频道信息列表
    
    返回:
        list: 处理后的频道信息列表
    """
    
    for channel in channels:
        name = channel['name']
        # 移除-MCP后缀
        if name.endswith('-MCP'):
            name = name[:-4]

            # 查找是否有其他同名频道
            for other_channel in channels:
                if name.lower() in other_channel['name'].lower():
                    channel['name'] = other_channel['name']
                    break

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


if __name__ == "__main__":
    # 测试功能
    print("=== IPTV 调度器测试 ===")
    
    # 执行配置更新
    print("\n--- 正在更新配置 ---")
    iptv_scheduler()
    
    # 显示配置信息
    # print("\n--- 配置信息 ---")
    # config = get_iptv_config()
    # if config:
    #     print(f"配置文件长度: {len(config)} 字符")
    #     print(f"前100个字符: {config[:100]}...")
    # else:
    #     print("配置文件为空或不存在")
    
    print("\n=== 测试完成 ===")
