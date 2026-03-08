"""
IPTV 配置定时更新模块

功能：
- 从多个源获取 IPTV 播放列表
- 检测频道可用性和流畅度（优化版 FFmpeg 检测）
- 合并并保存为 M3U 格式
"""

import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import CONFIG
from utils.logger import get_logger
from utils.iptv_checker import IPTVChecker
from models.channel import Channel

# ==================== 常量配置 ====================
IPTV_DIR = os.path.join(project_root, 'output', 'iptv')
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')
# 优化：平衡并发数（CPU 友好型）
# 根据 CPU 核心数动态调整，避免 CPU 过载
MAX_WORKERS = min(30, max(10, os.cpu_count() * 2)) if os.cpu_count() else 30

# 创建全局检测器实例（使用优化后的参数）
iptv_checker = IPTVChecker()

# 检查 ffmpeg 是否可用
FFMPEG_AVAILABLE = iptv_checker.is_ffmpeg_available()

os.makedirs(IPTV_DIR, exist_ok=True)
logger = get_logger('IPTV')

# ==================== 数据获取 ====================
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

# ==================== 解析函数 ====================
def parse_m3u(content: str) -> list:
    """
    解析 M3U 格式内容
    
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

def parse_txt(content: str) -> list:
    """
    解析 TXT 格式内容（频道名，URL）
    
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

def parse_url(url: str, content: str) -> list:
    """
    根据 URL 扩展名选择解析器
    """
    return parse_txt(content) if url.endswith('.txt') else parse_m3u(content)

# ==================== M3U 生成 ====================
def build_m3u(channels: list) -> str:
    """
    构建 M3U 格式内容
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

def merge_channels(urls: list) -> str:
    """
    合并多个 URL 的频道（边解析边去重）
    
    Args:
        urls: 源 URL 列表
    
    Returns:
        合并后的 M3U 内容
    """
    all_channels = []
    seen_urls = set()  # URL 去重
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
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
    
    # 检测频道可用性（GitHub Actions 中始终执行）
    valid_channels = iptv_checker.check_channels(all_channels, logger=logger, max_workers=MAX_WORKERS)
    return build_m3u(valid_channels)

# ==================== 文件操作 ====================
def save_file(filename: str, content: str) -> bool:
    """
    保存文件
    """
    if not content:
        return False

    path = os.path.join(IPTV_DIR, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"{filename} 已保存到 {path}")
        return True
    except Exception as e:
        logger.error(f"保存文件失败：{filename}, 错误：{e}")
        return False

# ==================== 主功能函数 ====================
def fetch_playlist():
    """从配置文件获取并合并播放列表"""
    if not os.path.exists(IPTV_URLS_FILE):
        logger.error(f"URL 配置文件不存在：{IPTV_URLS_FILE}")
        return

    try:
        with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        logger.error(f"读取 URL 配置文件失败：{e}")
        return

    if not urls:
        logger.error("URL 配置文件为空")
        return

    logger.info(f"正在从配置文件获取播放列表，读取到 {len(urls)} 个 URL...")
    content = merge_channels(urls)
    save_file('playlist.m3u', content)

def fetch_migu():
    """获取咪咕播放列表"""
    if not CONFIG.iptv.migu_url:
        logger.warning("Migu URL 未配置，跳过")
        return

    logger.info("正在获取 Migu 播放列表...")
    content = fetch_url(CONFIG.iptv.migu_url)
    
    if not content:
        logger.warning("Migu 播放列表获取失败，跳过")
        return
    
    save_file('migu.m3u', content)
    logger.info("Migu 播放列表获取完成, 共 {} 个频道".format(len(parse_m3u(content))))

def fetch_ott():
    """获取 OTT 播放列表"""
    if not CONFIG.iptv.ott_url:
        logger.warning("OTT URL 未配置，跳过")
        return

    logger.info("正在获取 OTT 播放列表...")
    content = fetch_url(CONFIG.iptv.ott_url)
    
    if not content:
        logger.warning("OTT 播放列表获取失败，跳过")
        return
    
    save_file('ott.m3u', content)
    logger.info("OTT 播放列表获取完成, 共 {} 个频道".format(len(parse_m3u(content))))

def fetch_github_playlist():
    """获取 GitHub 上的播放列表"""
    if not CONFIG.iptv.playlist_url:
        logger.warning("GitHub 播放列表 URL 未配置，跳过")
        return

    logger.info("正在获取 GitHub 播放列表...")
    content = fetch_url(CONFIG.iptv.playlist_url)
    
    if not content:
        logger.warning("GitHub 播放列表获取失败，跳过")
        return
    
    save_file('playlist.m3u', content)
    logger.info("GitHub 播放列表获取完成, 共 {} 个频道".format(len(parse_m3u(content))))


def iptv_scheduler_fetch_playlist():
    """IPTV 使用github actions来执行检测"""
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")

    fetch_playlist()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{duration:.2f}秒")

def iptv_scheduler():
    """IPTV 配置更新调度器"""
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")

    fetch_migu()
    fetch_ott()
    fetch_github_playlist()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{duration:.2f}秒")


def get_iptv_content(filename: str) -> str:
    """
    获取 IPTV 文件内容
    """
    path = os.path.join(IPTV_DIR, filename)
    try:
        return open(path, 'r', encoding='utf-8').read() if os.path.exists(path) else ""
    except Exception as e:
        logger.error(f"读取文件失败：{filename}, 错误：{e}")
        return ""

# ==================== 命令行入口 ====================
if __name__ == "__main__":
    # 执行调度器
    iptv_scheduler()
    # fetch_playlist()

    # 测试代码（需要时取消注释）
    # content = get_iptv_content('migu.m3u')
    # channels = parse_m3u(content)
    # logger.debug(f"共找到 {len(channels)} 个频道")
    # valid_channels = iptv_checker.check_channels(channels, logger=logger, max_workers=MAX_WORKERS)
    # logger.debug(f"有效频道数：{len(valid_channels)}")
    # logger.debug("\n测试结束\n")