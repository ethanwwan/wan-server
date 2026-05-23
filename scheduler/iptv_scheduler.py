"""
IPTV 配置定时更新模块

功能：
- 从多个源获取 IPTV 播放列表
- 检测频道可用性并生成播放列表

"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import CONFIG
from utils.logger import get_logger
from utils.iptv_utils import (
    fetch_url,
    parse_m3u,
    save_file,
    fetch_channels,
    build_m3u,
    sort_channels
)
from utils.iptv_checker import IPTVChecker

logger = get_logger('IPTV')
_iptv_checker = IPTVChecker()

MAX_WORKERS = min(30, max(10, os.cpu_count() * 2)) if os.cpu_count() else 30
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')


# ==================== 辅助函数 ====================

def _fetch_and_save(name: str, url: str, filename: str) -> bool:
    """
    通用函数：获取 URL 内容并保存
    
    Args:
        name: 来源名称（用于日志）
        url: 源 URL
        filename: 保存的文件名
    
    Returns:
        bool: 是否成功
    """
    if not url:
        logger.warning(f"{name} URL 未配置，跳过")
        return False
    
    logger.info(f"正在获取 {name} 播放列表...")
    content = fetch_url(url)
    
    if not content:
        logger.warning(f"{name} 播放列表获取失败，跳过")
        return False
    
    if save_file(filename, content):
        channel_count = len(parse_m3u(content))
        logger.info(f"{name} 播放列表获取完成，共 {channel_count} 个频道")
        return True
    return False


def _fetch_and_check_channels(urls: List[str], limit: Optional[int] = None) -> str:
    """
    从 URL 列表获取并检查频道可用性
    """
    all_channels = fetch_channels(urls, max_workers=MAX_WORKERS, limit=limit)
    
    if not all_channels:
        logger.warning("未获取到任何频道")
        return ''
    
    logger.info(f"开始检测 {len(all_channels)} 个频道的可用性...")
    
    valid_channels = []
    total_count = len(all_channels)
    checked_count = 0
    start_time = datetime.now()
    
    failure_reasons = {}
    alpha = 0.1
    avg_time_per_channel = 0.0
    
    def check_single_channel(channel: Dict) -> Tuple[Dict, Dict]:
        url = channel.get('url', '')
        name = channel.get('channel_name', '')
        try:
            result = _iptv_checker.check(url)
            return (channel, result)
        except Exception as e:
            error_type = type(e).__name__
            error_key = f"exception_{error_type}"
            return (channel, {'available': False, 'fluent': False, 'error': error_key})
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {executor.submit(check_single_channel, ch): ch for ch in all_channels}
        
        for future in as_completed(future_to_channel):
            channel, result = future.result()
            if result.get('available'):
                valid_channels.append(channel)
            else:
                error = result.get('error', 'unknown')
                failure_reasons[error] = failure_reasons.get(error, 0) + 1
            
            checked_count += 1
            
            current_elapsed = (datetime.now() - start_time).total_seconds()
            if checked_count == 1:
                avg_time_per_channel = current_elapsed
            else:
                instant_time = current_elapsed / checked_count
                avg_time_per_channel = alpha * instant_time + (1 - alpha) * avg_time_per_channel
            
            if checked_count % 500 == 0 or checked_count == total_count:
                progress = checked_count / total_count * 100
                remaining_channels = total_count - checked_count
                remaining_seconds = avg_time_per_channel * remaining_channels
                
                if remaining_seconds < 60:
                    remaining_str = f"{remaining_seconds:.0f}秒"
                elif remaining_seconds < 3600:
                    minutes = int(remaining_seconds // 60)
                    seconds = int(remaining_seconds % 60)
                    remaining_str = f"{minutes}分{seconds}秒"
                else:
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    remaining_str = f"{hours}小时{minutes}分"
                
                logger.info(f"检测进度: {checked_count}/{total_count} ({progress:.1f}%) - 可用: {len(valid_channels)} - 预计剩余: {remaining_str}")
    
    if failure_reasons:
        logger.info("=" * 60)
        logger.info("检测失败原因统计:")
        total_failed = sum(failure_reasons.values())
        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
            percentage = count / total_failed * 100
            logger.info(f"  {reason}: {count} 次 ({percentage:.1f}%)")
        logger.info("=" * 60)
    
    valid_channels = sort_channels(valid_channels)
    total_time = (datetime.now() - start_time).total_seconds()
    
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    time_str = f"{minutes}分{seconds}秒"
    
    logger.info(f"检测完成，可用频道: {len(valid_channels)}/{total_count}，总耗时: {time_str}")
    
    return build_m3u(valid_channels)


# ==================== 主功能函数 ====================

def fetch_ott() -> bool:
    """获取 OTT 播放列表"""
    return _fetch_and_save("OTT", CONFIG.iptv.ott_url, 'ott.m3u')


def fetch_playlist(limit: Optional[int] = None) -> bool:
    """
    获取播放列表并检测频道可用性
    
    执行流程：
    1. 从配置文件读取 URL 列表
    2. 获取频道并检测可用性
    3. 保存播放列表
    
    Args:
        limit: 限制获取的频道数量（可选）
    
    Returns:
        bool: 是否成功
    """
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")
    
    try:
        if not os.path.exists(IPTV_URLS_FILE):
            logger.error(f"URL 配置文件不存在：{IPTV_URLS_FILE}")
            return False
        
        with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            logger.error("URL 配置文件为空")
            return False
        
        logger.info(f"正在从配置文件获取播放列表，读取到 {len(urls)} 个 URL...")
        content = _fetch_and_check_channels(urls, limit)
        
        if content:
            if save_file('playlist.m3u', content):
                channel_count = len(parse_m3u(content))
                logger.info(f"播放列表合并完成，共保存 {channel_count} 个频道")
                return True
            logger.error("保存播放列表失败")
            return False
        else:
            logger.warning("本次检测未发现可用频道，保留上次的播放列表")
            return True
        
    except Exception as e:
        logger.error(f"IPTV 频道检测失败: {e}", exc_info=True)
        return False


# ==================== 调度器 ====================

def iptv_scheduler(limit: Optional[int] = None) -> bool:
    """
    IPTV 配置更新调度器
    
    执行流程：
    1. 获取 OTT 播放列表
    2. 获取播放列表并检测频道可用性
    
    Args:
        limit: 限制获取的频道数量（可选）
    
    Returns:
        bool: 是否成功
    """
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")
    
    try:
        ott_success = fetch_ott()
        playlist_success = fetch_playlist(limit)
        
        if ott_success or playlist_success:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{duration:.2f}秒"
            logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{time_str}")
            return True
        else:
            logger.error("所有播放列表获取失败")
            return False
            
    except Exception as e:
        logger.error(f"调度器执行错误: {e}")
        return False


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    iptv_scheduler()