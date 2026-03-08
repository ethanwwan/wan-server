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
from typing import List, Any

import requests
from models.channel import Channel
from utils.iptv_checker import IPTVChecker
import logging

logger = logging.getLogger("IPTV_UTILS")

# 最大并发数（CPU 友好型）
MAX_WORKERS = min(50, max(10, os.cpu_count() * 2)) if os.cpu_count() else 50

# 全局 IPTV 检测器实例
_iptv_checker = IPTVChecker()


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


def parse_m3u(content: str) -> List[Channel]:
    """
    解析 M3U 格式内容
    
    Args:
        content: M3U 格式文本内容
    
    Returns:
        Channel 对象列表
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

                channel = Channel(
                    channel_name=(comma.group(1).strip() if comma else "") or (tvg_name.group(1).strip() if tvg_name else ""),
                    url=url,
                    tvg_id=tvg_id.group(1).strip() if tvg_id else "",
                    tvg_name=tvg_name.group(1).strip() if tvg_name else "",
                    tvg_logo=tvg_logo.group(1).strip() if tvg_logo else "",
                    group_title=group.group(1).strip() if group else "",
                    type="video"
                )

                if channel.is_valid():
                    channels.append(channel)
        i += 1

    return channels


def parse_txt(content: str) -> List[Channel]:
    """
    解析 TXT 格式内容（频道名，URL）
    
    Args:
        content: TXT 格式文本内容（每行：频道名，URL）
    
    Returns:
        Channel 对象列表
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
                channel = Channel(
                    channel_name=name,
                    url=url,
                    tvg_id="",
                    tvg_name="",
                    tvg_logo="",
                    group_title="",
                    type="video"
                )
                
                if channel.is_valid():
                    channels.append(channel)

    return channels


def parse_url(url: str, content: str) -> List[Channel]:
    """
    根据 URL 扩展名选择解析器
    
    Args:
        url: 源 URL（用于判断文件类型）
        content: 文件内容
    
    Returns:
        Channel 对象列表
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
        # 支持 Channel 对象和字典两种格式
        if hasattr(ch, 'url'):
            # Channel 对象
            url = ch.url
            channel_name = ch.channel_name
            tvg_id = ch.tvg_id
            tvg_name = ch.tvg_name
            tvg_logo = ch.tvg_logo
            group_title = ch.group_title
        else:
            # 字典
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


def merge_channels(urls: List[str], max_workers: int = None) -> str:
    """
    合并多个 URL 的频道（边解析边去重）
    
    Args:
        urls: 源 URL 列表
        max_workers: 最大并发数，默认使用 MAX_WORKERS
    
    Returns:
        合并后的 M3U 内容
    """
    if max_workers is None:
        max_workers = MAX_WORKERS
        
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
    
    valid_channels = _iptv_checker.check_channels(all_channels, logger=logger, max_workers=max_workers)
    return build_m3u(valid_channels)


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


def is_ffmpeg_available() -> bool:
    """
    检查 FFmpeg 是否可用
    
    Returns:
        FFmpeg 是否可用
    """
    return _iptv_checker.is_ffmpeg_available()
