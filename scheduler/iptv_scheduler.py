"""
IPTV配置定时更新模块
"""

import os
import re
import shutil
import subprocess

FFMPEG_AVAILABLE = shutil.which('ffmpeg') is not None
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.config import CONFIG
from utils.logger import get_logger

IPTV_DIR = os.path.join(project_root, 'public', 'iptv')
IPTV_URLS_FILE = os.path.join(project_root, 'config', 'iptv_urls.txt')
MIGU_URL = CONFIG.iptv.migu_url
OTT_URL = CONFIG.iptv.ott_url

MAX_WORKERS = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
FPS_MIN = 24
os.makedirs(IPTV_DIR, exist_ok=True)

logger = get_logger('IPTV')


def fetch_url(url: str, timeout: int = 20) -> str:
    try:
        resp = requests.get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        content = resp.text.strip()
        # if len(content) < 10:
        #     logger.warning(f"内容过短，可能是空列表: {url}")
        return content
    except Exception as e:
        logger.error(f"请求失败: {url}, 错误: {e}")
        return ""


def parse_m3u(content: str) -> list:
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

                ch = {
                    'tvg_id': tvg_id.group(1).strip() if tvg_id else "",
                    'tvg_name': tvg_name.group(1).strip() if tvg_name else "",
                    'tvg_logo': tvg_logo.group(1).strip() if tvg_logo else "",
                    'group_title': group.group(1).strip() if group else "",
                    'channel_name': (comma.group(1).strip() if comma else "") or (tvg_name.group(1).strip() if tvg_name else ""),
                    'url': url
                }
                if ch['url'] and ch['channel_name']:
                    channels.append(ch)
        i += 1
    return channels


def parse_txt(content: str) -> list:
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
            if url.startswith('http://') or url.startswith('https://'):
                channels.append({
                    'tvg_id': "", 'tvg_name': "", 'tvg_logo': "",
                    'group_title': "", 'channel_name': name, 'url': url
                })
    return channels


def parse_url(url: str, content: str) -> list:
    return parse_txt(content) if url.endswith('.txt') else parse_m3u(content)


def check_url_available(url: str, timeout: int = 10) -> bool:
    """
    检测流媒体URL的基础可用性（是否能访问、是否为有效流）
    """
    logger.debug(f"[检测] 基础可用性: {url[:50]}...")
    
    cmd = [
        'ffmpeg',
        '-i', url,
        '-timeout', str(timeout * 1000000),
        '-http_seekable', '0',
        '-headers', f"User-Agent: {USER_AGENT}",
        '-t', '5',
        '-f', 'null', '-',
        '-v', 'error',
        '-hide_banner'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 2, text=True)
        error_log = result.stderr.lower()

        unavailable_keywords = [
            '404', 'not found', 'file not found',
            'connection refused',
            'connection timeout', 'connection timed out',
            'unable to open', 'server returned 403 forbidden',
            'invalid data found when processing input'
        ]

        if any(keyword in error_log for keyword in unavailable_keywords):
            return False

        if result.returncode != 0 and not any(keyword in error_log for keyword in unavailable_keywords):
            return True

        return True

    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_url_fluent(url: str, timeout: int = 15) -> bool:
    """
    检测流媒体URL的流畅性（基于可用性，额外校验帧率/音视频流/无卡顿）
    """
    logger.debug(f"[检测] 流畅度: {url[:50]}...")
    
    cmd = [
        'ffmpeg',
        '-i', url,
        '-timeout', str(timeout * 1000000),
        '-http_seekable', '0',
        '-headers', f"User-Agent: {USER_AGENT}",
        '-t', '10',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        '-hide_banner',
        '-'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 2, text=True)

        if result.returncode != 0:
            error_log = result.stderr.lower()
            if any(keyword in error_log for keyword in [
                'packet loss',
                'network is unreachable',
                'frame drop',
                'buffer underflow'
            ]):
                return False

        import json
        try:
            stream_info = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            return False

        has_video = False
        has_audio = False
        video_stream = None
        for stream in stream_info.get('streams', []):
            codec_type = stream.get('codec_type')
            if codec_type == 'video':
                has_video = True
                video_stream = stream
            elif codec_type == 'audio':
                has_audio = True

        if not has_video and not has_audio:
            return False

        if has_video and video_stream:
            fps_str = video_stream.get('r_frame_rate', '0/1')
            try:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den > 0 else 0.0
                if fps > 0 and fps < FPS_MIN:
                    return False
            except (ValueError, ZeroDivisionError):
                pass

        return True

    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_channel(ch: dict) -> dict:
    url = ch.get('url', '')
    if not url:
        return None
    
    channel_name = ch.get('channel_name', 'Unknown')
    
    if not check_url_available(url, 10):
        logger.debug(f"[不可用] {channel_name}: 基础可用性检测失败")
        return None
    
    if not check_url_fluent(url, 15):
        logger.debug(f"[不流畅] {channel_name}: 流畅度检测失败")
        return None
    
    logger.debug(f"[通过] {channel_name}: 可用且流畅")
    return ch


def check_channels(channels: list) -> list:
    channels = list({ch['url']: ch for ch in channels}.values())

    if not FFMPEG_AVAILABLE:
        logger.warning("ffmpeg 未安装，跳过频道有效性检测")
        return channels

    logger.info(f"开始检测频道有效性，共 {len(channels)} 个")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = [r for r in executor.map(check_channel, channels) if r]

    logger.info(f"频道有效性检测完成，有效: {len(results)}/{len(channels)}")
    return results


def build_m3u(channels: list) -> str:
    if not channels:
        return ""

    channels = check_channels(channels)
    lines = ['#EXTM3U']
    seen = set()

    for ch in channels:
        if ch['url'] in seen:
            continue
        seen.add(ch['url'])

        parts = []
        if ch['tvg_id']: parts.append(f'tvg-id="{ch["tvg_id"]}"')
        if ch['tvg_name']: parts.append(f'tvg-name="{ch["tvg_name"]}"')
        if ch['tvg_logo']: parts.append(f'tvg-logo="{ch["tvg_logo"]}"')
        if ch['group_title']: parts.append(f'group-title="{ch["group_title"]}"')

        lines.append(f'#EXTINF:-1 {" ".join(parts)},{ch["channel_name"]}')
        lines.append(ch['url'])

    return '\n'.join(lines)


def merge_channels(urls: list) -> str:
    all_channels = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            content = future.result()
            if content:
                all_channels.extend(parse_url(url, content))
    return build_m3u(all_channels)


def save_file(filename: str, content: str) -> bool:
    if not content:
        return False
    path = os.path.join(IPTV_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"{filename} 已保存到 {path}")
    return True


def fetch_playlist():
    if not os.path.exists(IPTV_URLS_FILE):
        logger.error(f"URL配置文件不存在: {IPTV_URLS_FILE}")
        return

    with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not urls:
        logger.error("URL配置文件为空")
        return

    logger.info(f"从配置文件读取到 {len(urls)} 个URL")
    content = merge_channels(urls)
    save_file('playlist.m3u', content)


def fetch_migu():
    if not MIGU_URL:
        logger.info("Migu URL未配置，跳过")
        return
    logger.info("正在获取Migu播放列表...")
    save_file('migu.m3u', fetch_url(MIGU_URL))


def fetch_ott():
    if not OTT_URL:
        logger.info("OTT URL未配置，跳过")
        return
    logger.info("正在获取OTT播放列表...")
    save_file('ott.m3u', fetch_url(OTT_URL))


def iptv_scheduler():
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")
    fetch_migu()
    fetch_ott()
    fetch_playlist()
    logger.info(f"配置更新完成，时间: {datetime.now().isoformat()}")


def get_iptv_content(filename: str) -> str:
    path = os.path.join(IPTV_DIR, filename)
    try:
        return open(path, 'r', encoding='utf-8').read() if os.path.exists(path) else ""
    except Exception as e:
        logger.error(f"读取文件失败: {filename}, 错误: {e}")
        return ""


if __name__ == "__main__":
    iptv_scheduler()
