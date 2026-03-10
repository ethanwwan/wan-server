"""
IPTV 工具类模块

提供 IPTV 相关的通用工具函数，包括：
- URL 内容获取
- M3U/TXT 格式解析
- M3U 文件生成
- 频道合并与去重
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Any, Dict

import requests
import logging

logger = logging.getLogger("IPTV_UTILS")

def fetch_url(url: str, timeout: int = 20) -> str:
    """
    从 URL 获取内容
    
    Args:
        url: 请求 URL
        timeout: 超时时间（秒）
    
    Returns:
        响应内容，失败返回空字符串
    """
    try:
        resp = requests.get(
            url, 
            timeout=timeout, 
            verify=False
        )
        resp.raise_for_status()
        content = resp.text.strip()
        
        if not content:
            logger.warning(f"URL 返回内容为空：{url}")
            return ""
        
        return content
    except requests.exceptions.Timeout:
        logger.error(f"请求超时：{url}, timeout={timeout}s")
        return ""
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP 错误：{url}, 状态码={e.response.status_code if e.response else 'N/A'}")
        return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败：{url}, 错误：{e}")
        return ""
    except Exception as e:
        logger.error(f"未知错误：{url}, 错误：{e}")
        return ""


def parse_m3u(content: str) -> List[Dict]:
    """
    解析 M3U 格式内容
    
    Args:
        content: M3U 格式文本内容
    
    Returns:
        频道字典列表
    """
    if not content:
        return []

    channels = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            url = lines[i + 1].strip()
            if url and not url.startswith('#'):
                ext_info = line
                tvg_id = re.search(r'tvg-id="([^"]*)"', ext_info)
                tvg_name = re.search(r'tvg-name="([^"]*)"', ext_info)
                tvg_logo = re.search(r'tvg-logo="([^"]*)"', ext_info)
                group = re.search(r'group-title="([^"]*)"', ext_info)
                comma = re.search(r',(.+)$', ext_info)

                channel = {
                    'channel_name': (comma.group(1).strip() if comma else "") or (tvg_name.group(1).strip() if tvg_name else ""),
                    'url': url,
                    'tvg_id': tvg_id.group(1).strip() if tvg_id else "",
                    'tvg_name': tvg_name.group(1).strip() if tvg_name else "",
                    'tvg_logo': tvg_logo.group(1).strip() if tvg_logo else "",
                    'group_title': group.group(1).strip() if group else ""
                }

                if channel.get('channel_name') and channel.get('url'):
                    channels.append(channel)
        i += 1

    return channels


def parse_txt(content: str) -> List[Dict]:
    """
    解析 TXT 格式内容（频道名，URL）
    
    Args:
        content: TXT 格式文本内容（每行：频道名，URL）
    
    Returns:
        频道字典列表
    """
    if not content:
        return []

    channels = []
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split(',')
        if len(parts) >= 2:
            name, url = parts[0].strip(), parts[1].strip()
            if url.startswith(('http://', 'https://')):
                channel = {
                    'channel_name': name,
                    'url': url,
                    'tvg_id': "",
                    'tvg_name': "",
                    'tvg_logo': "",
                    'group_title': ""
                }
                
                if channel.get('channel_name') and channel.get('url'):
                    channels.append(channel)

    return channels


def parse_url(url: str, content: str) -> List[Dict]:
    """
    根据 URL 扩展名选择解析器
    
    Args:
        url: 源 URL（用于判断文件类型）
        content: 文件内容
    
    Returns:
        频道字典列表
    """
    return parse_txt(content) if url.endswith('.txt') else parse_m3u(content)


def build_m3u(channels: List[Any]) -> str:
    """
    构建 M3U 格式内容
    
    Args:
        channels: Channel 对象列表或字典列表
    
    Returns:
        M3U 格式文本
    """
    if not channels:
        return ""
    
    lines = ['#EXTM3U x-tvg-url="https://gh-proxy.org/https://raw.githubusercontent.com/fanmingming/live/refs/heads/main/e.xml"']
    seen = set()
    
    for ch in channels:
        # 字典格式
        url = ch.get('url', '')
        channel_name = ch.get('channel_name', '')
        tvg_id = ch.get('tvg_id', '')
        tvg_name = ch.get('tvg_name', '')
        tvg_logo = ch.get('tvg_logo', '')
        group_title = ch.get('group_title', '')
        
        if url in seen:
            continue
        seen.add(url)
        
        parts = []
        if tvg_id:
            parts.append(f'tvg-id="{tvg_id}"')
        if tvg_name:
            parts.append(f'tvg-name="{tvg_name}"')
        if tvg_logo:
            parts.append(f'tvg-logo="{tvg_logo}"')
        if group_title:
            parts.append(f'group-title="{group_title}"')
        
        lines.append(f'#EXTINF:-1 {" ".join(parts)},{channel_name}')
        lines.append(url)
    
    return '\n'.join(lines)

def fetch_channels(urls: List[str], max_workers: int = 10) -> str:
    """
    合并多个 URL 的频道（边解析边去重）
    
    Args:
        urls: 源 URL 列表
        max_workers: 最大并发数，默认使用 MAX_WORKERS
    
    Returns:
        合并后的 M3U 内容
    """
        
    all_channels = []
    seen_urls = set()  # URL 去重
    
    logger.info(f"正在从 {len(urls)} 个 URL 获取频道...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    channels = parse_url(url, content)
                    # 边解析边去重
                    for ch in channels:
                        # 支持 Channel 对象和字典两种格式
                        ch_url = ch.url if hasattr(ch, 'url') else ch.get('url', '')
                        if ch_url not in seen_urls:
                            seen_urls.add(ch_url)
                            all_channels.append(ch)
            except Exception as e:
                logger.error(f"解析 URL 失败 {url}: {e}")
    
    logger.info(f"合并完成，共 {len(all_channels)} 个唯一频道")
    
    return all_channels


def save_file(filename: str, content: str, output_dir: str = None) -> bool:
    """
    保存文件
    
    Args:
        filename: 文件名
        content: 文件内容
        output_dir: 输出目录，默认为 output/iptv
    
    Returns:
        是否保存成功
    """
    if not content:
        return False
    
    if output_dir is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, 'output', 'iptv')
    
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"{filename} 已保存到 {path}")
        return True
    except Exception as e:
        logger.error(f"保存文件失败：{filename}, 错误：{e}")
        return False


def get_file_content(filename: str, input_dir: str = None) -> str:
    """
    获取文件内容
    
    Args:
        filename: 文件名（如 'migu.m3u', 'ott.m3u' 等）
        input_dir: 输入目录，默认为 output/iptv
    
    Returns:
        文件内容字符串，如果文件不存在或读取失败则返回空字符串
    """
    if input_dir is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        input_dir = os.path.join(project_root, 'output', 'iptv')
    
    path = os.path.join(input_dir, filename)
    if not os.path.exists(path):
        logger.warning(f"IPTV 文件不存在：{path}")
        return ""
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"成功读取 IPTV 文件：{filename}, 大小：{len(content)} 字节")
        return content
    except Exception as e:
        logger.error(f"读取文件失败：{filename}, 错误：{e}")
        return ""


GROUP_MAPPING = {
    '央视频道': ['央视'],
    '卫视频道': ['卫视'],
    '地方频道': ['地方', '浙江频道', '江苏频道', '广东频道', '湖南频道', '湖北频道', '四川频道', '河南频道', '河北频道', '山东频道', '山西频道', '陕西频道', '安徽频道', '福建频道', '江西频道', '辽宁频道', '吉林频道', '黑龙江频道', '北京频道', '上海频道', '天津频道', '重庆频道', '云南频道', '贵州频道', '广西频道', '海南频道', '甘肃频道', '青海频道', '内蒙古频道', '宁夏频道', '新疆频道', '西藏频道'],
    '电影电视': ['电影', '埋堆堆', '电视剧', '剧场', '影视'],
    '体育赛事': ['体育', '咪咕赛事'],
    '少儿教育': ['少儿', '动漫', '儿童', '动画'],
    '综艺娱乐': ['综艺', '音乐'],
    '纪录纪实': ['纪录', '直播中国', '纪实'],
    '国际全球': ['国际', '全球', '外语'],
    '港澳台': ['港·澳·台', '港澳', '港台'],
    '咪视界': ['咪视界', '咪视通'],
    'NewTV': ['NewTV'],
    'iHOT': ['IHOT'],
    'iPanda': ['ipanda']
}

CHANNEL_MAPPING = {
    '央视频道': ['CCTV', '央视', 'CGTN'],
    '卫视频道': ['卫视', '苏州4K'],
    '地方频道': ['北京', '上海', '广东', '浙江', '江苏', '湖南', '湖北', '四川', '重庆', '天津', '河北', '河南', '山东', '山西', '陕西', '江西', '福建', '安徽', '贵州', '云南', '广西', '海南', '黑龙江', '吉林', '辽宁', '内蒙古', '宁夏', '新疆', '青海', '甘肃', '西藏', '地方', '广州', '佛山', '江门', '汕头', '深圳', '珠海', '东莞', '中山', '惠州', '肇庆', '清远', '韶关', '河源', '梅州', '汕尾', '揭阳', '阳江', '茂名', '湛江', '潮州', '云浮', '南宁', '南京', '宁波', '杭州', '余杭', '上虞', '湖州', '松阳', '庆元', '民视', '余姚', '开化', '南国', '邢台', '绍兴', '嵊州', '新昌', '福州', '萧山', '钱江', '财经', '新闻综合'],
    '电影电视': ['电影'],
    '体育赛事': ['体育', '足球'],
    '少儿教育': ['少儿', '动画', '卡通', '动漫'],
    '综艺娱乐': ['综艺', '娱乐', '音乐'],
    '国际全球': ['国际','UK', '美亚'],
    '纪录纪实': ['纪录','人文', '历史', '地理', '自然', '生物', '纪实', '睛彩'],
    '港澳台': ['台湾', 'Taiwan', 'TVB', 'ATV', '公视', '华视', '台视', '中视', '东森', '中天', '凤凰', '澳亚', 'CHANNEL', 'CH5', 'CH8', '频道', 'VIUTV', 'RTHK', '明珠台', 'HOY', 'ASTRO', '欢喜台', 'AOD', 'AEC', 'QJ', '港·澳·台', '港澳', '港台'],
    '咪视界': ['咪视界', '咪视通'],
    'NewTV': ['NewTV'],
    'iHOT': ['IHOT'],
    'iPanda': ['ipanda']
}


def classify_channels(channels: List[Dict]) -> List[Dict]:
    """
    对频道进行分组优化
    
    匹配策略（按优先级）：
    1. 使用 group_mapping 匹配 group-title
    2. 未匹配的频道使用 channel_mapping 匹配 channel_name
    3. 仍未匹配的直接丢弃
    
    Args:
        channels: 频道列表 [{channel_name, url, group_title, ...}, ...]
    
    Returns:
        优化后的频道列表
    """
    group_mapping = GROUP_MAPPING
    channel_mapping = CHANNEL_MAPPING
    result = []

    logger.info(f"开始分类重组 {len(channels)} 个频道")
    
    for ch in channels:
        matched = False
        new_group = None
        
        group = ch.get('group_title', '')
        
        if group and '央卫视' not in group:
            for category, variants in group_mapping.items():
                for variant in variants:
                    if variant in group or group in variant:
                        new_group = category
                        matched = True
                        break
                if matched:
                    break
        
        if not matched:
            name = ch.get('channel_name', '')
            name_upper = name.upper()
            for category, keywords in channel_mapping.items():
                for keyword in keywords:
                    if keyword.upper() in name_upper or name_upper in keyword.upper():
                        new_group = category
                        matched = True
                        break
                if matched:
                    break
        
        if matched and new_group:
            ch['group_title'] = new_group
            result.append(ch)
    
    logger.info(f"分类重组完成，共 {len(result)} 个频道")

    return result