"""
IPTV 配置定时更新模块

功能：
- 从多个源获取 IPTV 播放列表
- 检测频道可用性并生成播放列表

"""

import os
import sys
import psutil
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

BATCH_SIZE = 300  # 分批处理大小
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')


def get_optimal_workers() -> int:
    """
    方案一：动态并发控制（基于系统负载）
    
    根据当前系统负载动态计算最优并发数，避免资源耗尽
    
    Returns:
        int: 最优并发数
    """
    cpu_count = os.cpu_count() or 2
    cpu_percent = psutil.cpu_percent()
    memory_percent = psutil.virtual_memory().percent
    
    # CPU 核心数基础并发
    base_workers = cpu_count * 2
    
    # 根据负载调整
    if cpu_percent > 80 or memory_percent > 80:
        # 高负载时降低并发
        workers = max(5, base_workers // 2)
        logger.info(f"系统高负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，降低并发数到 {workers}")
    elif cpu_percent > 60 or memory_percent > 60:
        # 中等负载时保持基础并发
        workers = base_workers
        logger.info(f"系统中等负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，使用基础并发数 {workers}")
    else:
        # 低负载时可以适当提高
        workers = min(30, int(base_workers * 1.5))
        logger.info(f"系统低负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，提高并发数到 {workers}")
    
    return workers


def get_current_workers() -> int:
    """
    获取当前推荐的并发数（动态）
    
    Returns:
        int: 当前并发数
    """
    return get_optimal_workers()


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
    从 URL 列表获取并检查频道可用性（方案一优化：动态并发控制）
    """
    # 获取动态并发数
    current_workers = get_current_workers()
    all_channels = fetch_channels(urls, max_workers=current_workers, limit=limit)
    
    if not all_channels:
        logger.warning("未获取到任何频道")
        return ''
    
    logger.info(f"开始检测 {len(all_channels)} 个频道的可用性...")
    
    # 分批处理，控制内存使用
    total_count = len(all_channels)
    batches = [all_channels[i:i+BATCH_SIZE] for i in range(0, total_count, BATCH_SIZE)]
    logger.info(f"共分为 {len(batches)} 批处理，每批最多 {BATCH_SIZE} 个频道")
    
    valid_channels = []
    checked_count = 0
    start_time = datetime.now()
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
    
    for batch_idx, batch in enumerate(batches, 1):
        # 每批开始时重新计算并发数（动态调整）
        current_workers = get_current_workers()
        logger.info(f"正在处理第 {batch_idx}/{len(batches)} 批，共 {len(batch)} 个频道，并发数: {current_workers}")
        
        with ThreadPoolExecutor(max_workers=current_workers) as executor:
            future_to_channel = {executor.submit(check_single_channel, ch): ch for ch in batch}
            
            for future in as_completed(future_to_channel):
                channel, result = future.result()
                if result.get('available'):
                    valid_channels.append(channel)
                else:
                    # 方案一优化：保存失败记录到缓存
                    from utils.iptv_utils import _save_fail_cache
                    _save_fail_cache(channel.get('url', ''))
                
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
        
        # 释放内存
        del batch
    
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
        # 执行 OTT 播放列表获取
        ott_success = fetch_ott()
        if ott_success:
            logger.info("OTT 播放列表获取成功")
        else:
            logger.warning("OTT 播放列表获取失败")
        
        # 执行播放列表获取和检测
        playlist_success = fetch_playlist(limit)
        if playlist_success:
            logger.info("Playlist 播放列表获取和检测成功")
        else:
            logger.warning("Playlist 播放列表获取和检测失败")
        
        # 汇总结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{duration:.2f}秒"
        
        if ott_success or playlist_success:
            logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{time_str}")
            return True
        else:
            logger.error(f"所有播放列表获取失败，时间：{end_time.isoformat()}，耗时：{time_str}")
            return False
            
    except Exception as e:
        logger.error(f"调度器执行错误: {e}")
        return False


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    iptv_scheduler()