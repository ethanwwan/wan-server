"""
IPTV 配置定时更新模块

功能：
- 从多个源获取 IPTV 播放列表
- 检测频道可用性和流畅度
- 合并并保存为 M3U 格式
"""

import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.config import CONFIG
from utils.logger import get_logger

# ==================== 常量配置 ====================

IPTV_DIR = os.path.join(project_root, 'public', 'iptv')
IPTV_URLS_FILE = os.path.join(project_root, 'config', 'iptv_urls.txt')

MIGU_URL = CONFIG.iptv.migu_url
OTT_URL = CONFIG.iptv.ott_url

MAX_WORKERS = 30
FPS_MIN = 20

FFMPEG_AVAILABLE = shutil.which('ffmpeg') is not None

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
        resp = requests.get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp.text.strip()
    except Exception as e:
        logger.error(f"请求失败：{url}, 错误：{e}")
        return ""


# ==================== 解析函数 ====================

def parse_m3u(content: str) -> list:
    """
    解析 M3U 格式内容

    Args:
        content: M3U 文件内容

    Returns:
        频道列表
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
    """
    解析 TXT 格式内容（频道名，URL）

    Args:
        content: TXT 文件内容

    Returns:
        频道列表
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
                channels.append({
                    'tvg_id': "",
                    'tvg_name': "",
                    'tvg_logo': "",
                    'group_title': "",
                    'channel_name': name,
                    'url': url
                })

    return channels


def parse_url(url: str, content: str) -> list:
    """
    根据 URL 扩展名选择解析器

    Args:
        url: 源 URL
        content: 文件内容

    Returns:
        频道列表
    """
    return parse_txt(content) if url.endswith('.txt') else parse_m3u(content)


# ==================== 频道检测 ====================

def _build_ffmpeg_cmd(url: str, mode: str, duration: str) -> list:
    """
    构建 ffmpeg 检测命令

    Args:
        url: 检测 URL
        mode: 日志模式 
        duration: 检测时长（秒）

    Returns:
        ffmpeg 命令列表
    """
    return [
        'ffmpeg',
        '-i', url,
        '-t', duration,
        '-f', 'null', '-',
        '-probesize', '32',   
        '-v', mode,
        '-hide_banner'
    ]


def _check_ffmpeg_error(stderr: str) -> bool:
    """
    检查 ffmpeg 错误日志

    Args:
        stderr: ffmpeg 错误输出

    Returns:
        是否包含严重错误
    """
    error_log = stderr.lower()
    keywords = [
        '404', 'not found', 'file not found',
        'connection refused',
        'connection timeout', 'connection timed out',
        'unable to open', 'server returned 403 forbidden',
        'invalid data found when processing input'
    ]
    return any(keyword in error_log for keyword in keywords)


def check_url_available(url: str, timeout: int = 10) -> bool:
    """
    检查 URL 是否可用（基础检测）

    Args:
        url: 检测 URL
        timeout: 超时时间（秒）

    Returns:
        是否可用
    """
    logger.debug(f"[基础检测] timeout={timeout}s: {url[:50]}...")

    cmd = _build_ffmpeg_cmd(url, 'error', '3')

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            logger.debug(f"[超时] {url[:50]}...")
            return False

        logger.debug(f"returncode={process.returncode}, stderr={len(stderr)} chars")

        if _check_ffmpeg_error(stderr):
            logger.debug(f"[失败] 命中错误关键词")
            return False

        logger.debug(f"[通过] returncode={process.returncode}")
        return True

    except Exception as e:
        logger.debug(f"[异常] {e}")
        return False


def check_url_fluent(url: str, timeout: int = 20) -> bool:
    """
    检查 URL 是否流畅（流畅度检测）

    Args:
        url: 检测 URL
        timeout: 超时时间（秒）

    Returns:
        是否流畅
    """
    logger.debug(f"[流畅检测] timeout={timeout}s: {url[:50]}...")

    cmd = _build_ffmpeg_cmd(url, 'verbose', '6')

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            logger.debug(f"[超时] {url[:50]}...")
            return False

        logger.debug(f"returncode={process.returncode}, stderr={len(stderr)} chars")
        error_log = stderr.lower()

        # 检查是否有帧输出
        if 'frame=' in error_log and 'fps=' in error_log:
            stream_fps_matches = re.findall(r'video:.*?(\d+)\s+fps', error_log, re.IGNORECASE)

            if stream_fps_matches:
                fps = float(stream_fps_matches[0])
                logger.debug(f"[视频] fps={fps:.2f}, min={FPS_MIN}")

                if fps > 0 and fps < FPS_MIN:
                    logger.debug(f"[失败] 帧率低于阈值")
                    return False
            else:
                proc_fps_matches = re.findall(r'frame=\s*\d+\s+fps=(\d+\.?\d*)', error_log)
                if proc_fps_matches:
                    logger.debug(f"[视频] 无法获取源视频帧率，仅检测到处理速度")
                else:
                    logger.debug(f"[视频] 无法提取 fps")

            logger.debug(f"[通过] 检测到正常播放帧")
            return True

        # 检查错误
        keywords = [
            '404', 'not found', 'file not found',
            'connection refused',
            'connection timeout', 'connection timed out',
            'unable to open', 'server returned 403',
            'invalid data', 'option not found'
        ]

        if any(keyword in error_log for keyword in keywords):
            logger.debug(f"[失败] 命中错误关键词")
            return False

        if process.returncode == 0:
            logger.debug(f"[通过] returncode=0")
            return True

        logger.debug(f"[失败] 未获取到有效信息")
        return False

    except Exception as e:
        logger.debug(f"[异常] {e}")
        return False


def check_channel(ch: dict) -> dict:
    """
    检测单个频道

    Args:
        ch: 频道信息字典

    Returns:
        通过检测的频道信息，失败返回 None
    """
    url = ch.get('url', '')
    channel_name = ch.get('channel_name', '')

    if not url or not channel_name:
        return None

    if not check_url_available(url, 10):
        logger.debug(f"[不可用] {channel_name}: 基础可用性检测失败")
        return None

    if not check_url_fluent(url, 20):
        logger.debug(f"[不流畅] {channel_name}: 流畅度检测失败")
        return None

    logger.debug(f"[通过] {channel_name}: 可用且流畅")
    return ch


def check_channels(channels: list) -> list:
    """
    批量检测频道

    Args:
        channels: 频道列表

    Returns:
        通过检测的频道列表
    """
    # 去重
    channels = list({ch['url']: ch for ch in channels}.values())

    if not FFMPEG_AVAILABLE:
        logger.warning("ffmpeg 未安装，跳过频道有效性检测")
        return channels

    logger.info(f"开始检测频道有效性，共 {len(channels)} 个")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = [r for r in executor.map(check_channel, channels) if r]

    logger.info(f"频道有效性检测完成，有效：{len(results)}/{len(channels)}")
    return results


# ==================== M3U 生成 ====================

def build_m3u(channels: list) -> str:
    """
    构建 M3U 格式内容

    Args:
        channels: 频道列表

    Returns:
        M3U 格式字符串
    """
    if not channels:
        return ""

    lines = ['#EXTM3U']
    seen = set()

    for ch in channels:
        if ch['url'] in seen:
            continue
        seen.add(ch['url'])

        parts = []
        if ch['tvg_id']:
            parts.append(f'tvg-id="{ch["tvg_id"]}"')
        if ch['tvg_name']:
            parts.append(f'tvg-name="{ch["tvg_name"]}"')
        if ch['tvg_logo']:
            parts.append(f'tvg-logo="{ch["tvg_logo"]}"')
        if ch['group_title']:
            parts.append(f'group-title="{ch["group_title"]}"')

        lines.append(f'#EXTINF:-1 {" ".join(parts)},{ch["channel_name"]}')
        lines.append(ch['url'])

    return '\n'.join(lines)


def merge_channels(urls: list) -> str:
    """
    合并多个 URL 的频道

    Args:
        urls: URL 列表

    Returns:
        合并后的 M3U 内容
    """
    all_channels = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            content = future.result()
            if content:
                all_channels.extend(parse_url(url, content))

    return build_m3u(all_channels)


# ==================== 文件操作 ====================

def save_file(filename: str, content: str) -> bool:
    """
    保存文件

    Args:
        filename: 文件名
        content: 文件内容

    Returns:
        是否保存成功
    """
    if not content:
        return False

    path = os.path.join(IPTV_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"{filename} 已保存到 {path}")
    return True


# ==================== 主功能函数 ====================

def fetch_playlist():
    """从配置文件获取并合并播放列表"""
    if not os.path.exists(IPTV_URLS_FILE):
        logger.error(f"URL 配置文件不存在：{IPTV_URLS_FILE}")
        return

    with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not urls:
        logger.error("URL 配置文件为空")
        return

    logger.info(f"正在从配置文件获取播放列表，读取到 {len(urls)} 个 URL...")
    content = merge_channels(urls)
    save_file('playlist.m3u', content)


def fetch_migu():
    """获取咪咕播放列表"""
    if not MIGU_URL:
        logger.warning("Migu URL 未配置，跳过")
        return

    logger.info("正在获取 Migu 播放列表...")
    save_file('migu.m3u', fetch_url(MIGU_URL))


def fetch_ott():
    """获取 OTT 播放列表"""
    if not OTT_URL:
        logger.warning("OTT URL 未配置，跳过")
        return

    logger.info("正在获取 OTT 播放列表...")
    save_file('ott.m3u', fetch_url(OTT_URL))


def iptv_scheduler():
    """IPTV 配置更新调度器"""
    logger.info(f"开始更新配置，时间：{datetime.now().isoformat()}")

    fetch_migu()
    fetch_ott()
    fetch_playlist()

    logger.info(f"配置更新完成，时间：{datetime.now().isoformat()}")


def get_iptv_content(filename: str) -> str:
    """
    获取 IPTV 文件内容

    Args:
        filename: 文件名

    Returns:
        文件内容
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
    # iptv_scheduler()

    # 测试代码（需要时取消注释）
    content = get_iptv_content('ott.m3u')
    channels = parse_m3u(content)
    logger.debug(f"共找到 {len(channels)} 个频道")
    check_channels(channels)
    logger.debug("\n测试结束\n")
