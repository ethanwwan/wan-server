import os
import sys
import psutil
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

aggregator_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(aggregator_root)
for p in [project_root, aggregator_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from logger import get_logger

from utils.iptv_utils import (
    fetch_url,
    parse_m3u,
    save_file,
    fetch_channels,
    build_m3u,
    sort_channels
)
from utils.iptv_checker import IPTVChecker
from utils.cache_manager import get_cache_manager
from utils.iptv_config import get_input_file_path, IPTV_CONFIG, get_output_dir

logger = get_logger('IPTV')
_iptv_checker = IPTVChecker()

# 硬编码配置
OTT_URL = "https://live.ottiptv.cc/iptv.m3u?userid=7755950497&sign=b7578005974939b989b3895b921110bcb06c83ed6f42b7139ba8b94c719484c980303585b7a1ffcc75c631fb0e9e8cd3983d6dc87447c558c9dc7770f76795671c177a0ad46048&auth_token=17b0d6712a2beb7e9bfea802dc9d33a3"


def get_optimal_workers(default_workers: int = IPTV_CONFIG.DEFAULT_WORKERS) -> int:
    """
    动态并发控制（基于系统负载）

    如果指定了 default_workers，则直接返回该值

    Args:
        default_workers: 指定的并发数，如果为 None 则根据系统负载动态计算

    Returns:
        int: 最优并发数
    """
    if default_workers is not None:
        return default_workers

    cpu_count = os.cpu_count() or 2
    cpu_percent = psutil.cpu_percent()
    memory_percent = psutil.virtual_memory().percent

    base_workers = cpu_count * 2

    if cpu_percent > 80 or memory_percent > 80:
        workers = max(5, base_workers // 2)
        logger.info(f"系统高负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，降低并发数到 {workers}")
    elif cpu_percent > 60 or memory_percent > 60:
        workers = base_workers
        logger.info(f"系统中等负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，使用基础并发数 {workers}")
    else:
        workers = min(IPTV_CONFIG.MAX_WORKERS, int(base_workers * 1.5))
        logger.info(f"系统低负载 (CPU:{cpu_percent}%, MEM:{memory_percent}%)，提高并发数到 {workers}")

    return workers


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


def _check_single_channel(channel: Dict) -> Tuple[Dict, Dict]:
    """
    检测频道可用性（无重试机制，失败即加入缓存）

    Args:
        channel: 频道信息

    Returns:
        Tuple[Dict, Dict]: (channel, result)
    """
    url = channel.get('url', '')
    name = channel.get('channel_name', '')

    try:
        result = _iptv_checker.check(url)
        if not result.get('available'):
            error = result.get('error', 'unknown')
            logger.debug(f"[检测策略] 检测失败: {name} - 错误类型: {error}")
        return (channel, result)
    except Exception as e:
        error_type = type(e).__name__
        error_key = f"exception_{error_type}"
        logger.debug(f"[检测策略] 检测异常: {name} - 异常类型: {error_key}")
        return (channel, {'available': False, 'fluent': False, 'error': error_key})


def _generate_report(total_count: int, valid_count: int, failed_count: int, total_time: float):
    """
    生成检测统计报告

    Args:
        total_count: 总检测频道数
        valid_count: 可用频道数
        failed_count: 失败频道数
        total_time: 总耗时（秒）
    """
    success_rate = (valid_count / total_count) * 100 if total_count > 0 else 0

    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    report = f"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    IPTV 频道检测统计报告                                 ║
╠══════════════════════════════════════════════════════════════════════════╣
║ 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║ 【频道统计】                                                             ║
║   总检测频道: {total_count:>6d} 个                                       ║
║   可用频道:   {valid_count:>6d} 个                                       ║
║   失败频道:   {failed_count:>6d} 个                                       ║
║   成功率:     {success_rate:>6.2f}%                                     ║
╠══════════════════════════════════════════════════════════════════════════╣
║ 【性能统计】                                                             ║
║   总耗时:     {minutes:>3d}分{seconds:>2d}秒                            ║
║   平均耗时:   {(total_time / total_count):>6.2f}秒/频道                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║ 【策略执行】                                                             ║
║   ✓ 缓存策略: 单例模式 + 批量更新                                         ║
║   ✓ 检测策略: 动态并发控制，无重试机制                                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

    if save_file('playlist_report.txt', report):
        logger.info(f"[检测策略] 统计报告已保存到 output/iptv/playlist_report.txt")
    else:
        logger.warning("[检测策略] 统计报告保存失败")


def _fetch_and_check_channels(urls: List[str], limit: Optional[int] = None) -> str:
    """
    从 URL 列表获取并检查频道可用性
    """
    current_workers = get_optimal_workers()
    logger.info(f"[检测策略] 初始并发数: {current_workers}")

    # 周日清空缓存
    if datetime.now().weekday() == 6:
        cache_manager = get_cache_manager()
        cache_manager.clear_all()
        logger.info("[缓存策略] 周日检测，已清空所有缓存")

    all_channels = fetch_channels(urls, max_workers=current_workers, limit=limit)

    if not all_channels:
        logger.warning("[检测策略] 未获取到任何频道")
        return ''

    logger.info(f"[检测策略] 开始检测 {len(all_channels)} 个频道的可用性...")

    total_count = len(all_channels)
    batches = [all_channels[i:i+IPTV_CONFIG.BATCH_SIZE] for i in range(0, total_count, IPTV_CONFIG.BATCH_SIZE)]
    logger.info(f"[检测策略] 共分为 {len(batches)} 批处理，每批最多 {IPTV_CONFIG.BATCH_SIZE} 个频道")

    valid_channels = []
    checked_count = 0
    failed_count = 0
    start_time = datetime.now()
    avg_time_per_channel = 0.0

    success_urls_batch = []
    failed_urls_batch = []
    cache_manager = get_cache_manager()

    for batch_idx, batch in enumerate(batches, 1):
        current_workers = get_optimal_workers()
        logger.info(f"[检测策略] 正在处理第 {batch_idx}/{len(batches)} 批，共 {len(batch)} 个频道，并发数: {current_workers}")

        with ThreadPoolExecutor(max_workers=current_workers) as executor:
            future_to_channel = {executor.submit(_check_single_channel, ch): ch for ch in batch}

            for future in as_completed(future_to_channel):
                channel, result = future.result()

                if result.get('available'):
                    valid_channels.append(channel)
                    success_urls_batch.append(channel.get('url', ''))
                else:
                    failed_count += 1
                    failed_urls_batch.append(channel.get('url', ''))

                checked_count += 1

                current_elapsed = (datetime.now() - start_time).total_seconds()
                if checked_count == 1:
                    avg_time_per_channel = current_elapsed
                else:
                    instant_time = current_elapsed / checked_count
                    avg_time_per_channel = 0.1 * instant_time + 0.9 * avg_time_per_channel

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

                    logger.info(f"[检测策略] 进度: {checked_count}/{total_count} ({progress:.1f}%) - 可用: {len(valid_channels)} - 失败: {failed_count} - 预计剩余: {remaining_str}")

        # 批量更新缓存
        if success_urls_batch or failed_urls_batch:
            cache_manager.batch_update(
                successes=tuple(success_urls_batch),
                failures=tuple(failed_urls_batch)
            )
            success_urls_batch.clear()
            failed_urls_batch.clear()

        del batch

    valid_channels = sort_channels(valid_channels)
    total_time = (datetime.now() - start_time).total_seconds()

    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    time_str = f"{minutes}分{seconds}秒"

    logger.info(f"[检测策略] 检测完成，可用频道: {len(valid_channels)}/{total_count}，失败: {failed_count}，总耗时: {time_str}")

    # 保存缓存到磁盘
    cache_manager.save_to_disk()

    # 生成统计报告
    _generate_report(total_count, len(valid_channels), failed_count, total_time)

    return build_m3u(valid_channels)


def fetch_ott() -> bool:
    """获取 OTT 播放列表"""
    return _fetch_and_save("OTT", OTT_URL, 'ott.m3u')


def fetch_playlist(limit: Optional[int] = None) -> bool:
    """
    获取播放列表并检测频道可用性（核心功能）

    Args:
        limit: 限制获取的频道数量（可选）

    Returns:
        bool: 是否成功
    """
    try:
        iptv_urls_file = get_input_file_path('iptv_urls.txt')

        if not os.path.exists(iptv_urls_file):
            logger.error(f"URL 配置文件不存在：{iptv_urls_file}")
            return False

        with open(iptv_urls_file, 'r', encoding='utf-8') as f:
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


def iptv_scheduler(limit: Optional[int] = None) -> bool:
    """
    IPTV 配置更新调度器

    Args:
        limit: 限制获取的频道数量（可选）

    Returns:
        bool: 是否成功
    """
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")

    try:
        ott_success = fetch_ott()
        if ott_success:
            logger.info("OTT 播放列表获取成功")
        else:
            logger.warning("OTT 播放列表获取失败")

        playlist_success = fetch_playlist(limit)
        if playlist_success:
            logger.info("Playlist 播放列表获取和检测成功")
        else:
            logger.warning("Playlist 播放列表获取和检测失败")

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
