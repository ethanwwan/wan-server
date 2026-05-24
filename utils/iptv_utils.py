"""
IPTV 工具类模块

提供 IPTV 相关的通用工具函数，包括：
- URL 内容获取
- M3U/TXT 格式解析
- M3U 文件生成
- 频道合并与去重
- 频道分类
"""

import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import logging

import requests

from .iptv_config import get_project_root, get_output_dir, IPTVConfig

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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        resp = requests.get(
            url, 
            timeout=timeout, 
            verify=False,
            headers=headers
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
                
                channel_name = ""
                if tvg_name:
                    channel_name = tvg_name.group(1).strip()
                elif comma:
                    raw_name = comma.group(1).strip()
                    if '=' in raw_name:
                        parts = raw_name.split(',')
                        channel_name = parts[-1].strip() if parts else raw_name
                    else:
                        channel_name = raw_name

                channel = {
                    'channel_name': channel_name,
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


def build_m3u(channels: List[Dict]) -> str:
    """
    构建 M3U 格式内容
    
    Args:
        channels: 频道字典列表
    
    Returns:
        M3U 格式文本
    """
    if not channels:
        return ""
    
    lines = ['#EXTM3U x-tvg-url="https://gh-proxy.org/https://raw.githubusercontent.com/fanmingming/live/refs/heads/main/e.xml"']
    seen = set()
    
    for ch in channels:
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


def filter_channels(channels: List[Dict]) -> List[Dict]:
    """
    过滤无效频道
    
    过滤规则：
    1. 重复 URL 过滤
    2. 无效协议过滤
    3. 历史失败记录过滤（已确认失败的频道）
    
    Args:
        channels: 原始频道列表
    
    Returns:
        过滤后的频道列表
    """
    from .cache_manager import get_cache_manager
    
    seen_urls = set()
    filtered = []
    skipped_cache = 0
    
    cache_manager = get_cache_manager()
    fail_cache = cache_manager.get_cache()
    
    for ch in channels:
        url = ch.get('url', '')
        
        # 1. 无效协议过滤
        if not url.startswith(('http://', 'https://')):
            logger.debug(f"跳过无效协议: {url}")
            continue
        
        # 2. 重复 URL 过滤
        if url in seen_urls:
            logger.debug(f"跳过重复 URL: {url}")
            continue
        seen_urls.add(url)
        
        # 3. 历史失败记录过滤
        if url in fail_cache and not cache_manager.is_expired(url):
            skipped_cache += 1
            logger.debug(f"跳过历史失败 URL: {url} (失败次数: {fail_cache[url].get('fail_count', 0)})")
            continue
        
        filtered.append(ch)
    
    logger.info(f"[缓存策略] 过滤完成: 原始 {len(channels)} 个频道，跳过 {skipped_cache} 个缓存失败频道，保留 {len(filtered)} 个待检测频道")
    return filtered


def classify_channels(channels: List[Dict], keep_unmatched: bool = False) -> List[Dict]:
    """
    频道分类重组
    
    Args:
        channels: 原始频道列表
        keep_unmatched: 是否保留未匹配的频道（归类为"其他"）
    
    Returns:
        分类后的频道列表
    """
    config = IPTVConfig.build()
    group_mapping = config.GROUP_MAPPING
    channel_mapping = config.CHANNEL_MAPPING
    
    result = []
    
    for ch in channels:
        name = ch.get('channel_name', '').upper()
        group_title = ch.get('group_title', '').upper()
        new_group = '其他'
        cleaned_name = name.replace('【', '').replace('】', '').replace('[', '').replace(']', '').strip()
        
        for group, keywords in group_mapping.items():
            if any(kw.upper() in group_title for kw in keywords):
                new_group = group
                break
        
        if new_group == '其他':
            for group, keywords in channel_mapping.items():
                if any(kw.upper() in name for kw in keywords):
                    new_group = group
                    break
        
        ch['group_title'] = new_group
        
        if new_group != '其他' or keep_unmatched:
            result.append(ch)
    
    return result


def fetch_channels(urls: List[str], max_workers: int = 10, limit: int = None) -> List[Dict]:
    """
    合并多个 URL 的频道（边解析边去重）
    
    Args:
        urls: 源 URL 列表
        max_workers: 最大并发数
        limit: 需要获取的频道数量，None 表示获取所有
    
    Returns:
        合并后的频道列表
    """
    all_channels = []
    seen_urls = set()
    
    logger.info(f"正在从 {len(urls)} 个 URL 获取频道...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    channels = parse_url(url, content)
                    for ch in channels:
                        ch_url = ch.url if hasattr(ch, 'url') else ch.get('url', '')
                        if ch_url not in seen_urls:
                            seen_urls.add(ch_url)
                            all_channels.append(ch)
                            if limit and len(all_channels) >= limit:
                                break
            except Exception as e:
                logger.error(f"解析 URL 失败 {url}: {e}")
            
            if limit and len(all_channels) >= limit:
                break
    
    logger.info(f"合并完成，共 {len(all_channels)} 个唯一频道")
    
    all_channels = filter_channels(all_channels)
    all_channels = classify_channels(all_channels)
    
    logger.info(f"分类重组完成，剩余 {len(all_channels)} 个频道")
    
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
        output_dir = get_output_dir()
    
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
        filename: 文件名
        input_dir: 输入目录，默认为 output/iptv
    
    Returns:
        文件内容字符串，如果文件不存在或读取失败则返回空字符串
    """
    if input_dir is None:
        input_dir = get_output_dir()
    
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


def sort_channels(channels: List[Dict]) -> List[Dict]:
    """
    按频道组排序
    
    Args:
        channels: 频道列表
    
    Returns:
        排序后的频道列表
    """
    group_order = [
        '央视频道', '卫视频道', '地方频道', '电影电视', '体育赛事',
        '少儿教育', '综艺娱乐', '纪录纪实', '国际全球', '港澳台',
        '咪视界', 'NewTV', 'iHOT', 'iPanda', '其他'
    ]
    
    def sort_key(ch):
        group = ch.get('group_title', '其他')
        name = ch.get('channel_name', '')
        try:
            return (group_order.index(group), name)
        except ValueError:
            return (len(group_order), name)
    
    return sorted(channels, key=sort_key)