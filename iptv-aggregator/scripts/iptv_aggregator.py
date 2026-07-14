import os
import sys
import psutil
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

iptv_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(iptv_root)
for p in [project_root, iptv_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from logger import get_logger

from iptv_utils import (
    save_file, fetch_channels, parse_m3u, build_m3u, sort_channels,
    get_input_file_path, IPTV_CONFIG, get_output_dir, get_cache_manager
)
from iptv_checker import IPTVChecker

logger = get_logger('IPTV')
_iptv_checker = IPTVChecker()


_last_workers = IPTV_CONFIG.DEFAULT_WORKERS

def get_optimal_workers() -> int:
    global _last_workers
    cpu_count = os.cpu_count() or 2
    cpu_percent = psutil.cpu_percent()
    memory_percent = psutil.virtual_memory().percent
    base = cpu_count * 2
    if cpu_percent > 80 or memory_percent > 80:
        w = max(5, base // 2)
    elif cpu_percent > 60 or memory_percent > 60:
        w = base
    else:
        w = min(IPTV_CONFIG.MAX_WORKERS, int(base * 1.5))
    w = max(20, w)
    if w != _last_workers:
        logger.info(f"并发 {_last_workers}->{w} (CPU:{cpu_percent}%, MEM:{memory_percent}%)")
        _last_workers = w
    return w


def _check_single_channel(channel: Dict) -> Tuple[Dict, Dict]:
    url = channel.get('url', '')
    name = channel.get('channel_name', '')
    try:
        result = _iptv_checker.check(url)
        if not result.get('available'):
            logger.debug(f"检测失败: {name} - {result.get('error', 'unknown')}")
        return (channel, result)
    except Exception as e:
        logger.debug(f"检测异常: {name} - {type(e).__name__}")
        return (channel, {'available': False, 'fluent': False, 'error': f'exception_{type(e).__name__}'})


def _fetch_and_check_channels(urls: List[str], limit: Optional[int] = None) -> str:
    if datetime.now().weekday() == 6:
        cache_manager = get_cache_manager()
        cache_manager.clear_all()
        logger.info("[缓存] 周日清空")

    all_channels = fetch_channels(urls, max_workers=10, limit=limit)
    if not all_channels:
        logger.warning("未获取到频道")
        return ''

    logger.info(f"开始检测 {len(all_channels)} 个频道...")
    total_count = len(all_channels)
    batches = [all_channels[i:i+IPTV_CONFIG.BATCH_SIZE] for i in range(0, total_count, IPTV_CONFIG.BATCH_SIZE)]
    logger.info(f"共 {len(batches)} 批，每批 ≤{IPTV_CONFIG.BATCH_SIZE}")

    valid_channels = []
    checked_count = 0
    failed_count = 0
    start_time = datetime.now()
    avg_time = 0.0
    success_batch = []
    failed_batch = []
    cache_manager = get_cache_manager()

    for bidx, batch in enumerate(batches, 1):
        current_workers = get_optimal_workers()
        logger.info(f"处理第 {bidx}/{len(batches)} 批 ({len(batch)} 个, 并发 {current_workers})")
        with ThreadPoolExecutor(max_workers=current_workers) as executor:
            futs = {executor.submit(_check_single_channel, ch): ch for ch in batch}
            for fut in as_completed(futs):
                channel, result = fut.result()
                url = channel.get('url', '')
                if result.get('available') and result.get('fluent'):
                    valid_channels.append(channel)
                    success_batch.append(url)
                elif result.get('available') and not result.get('fluent'):
                    failed_count += 1
                    failed_batch.append((url, 'low_quality'))
                else:
                    failed_count += 1
                    failed_batch.append((url, 'fail'))
                checked_count += 1
                elapsed = (datetime.now() - start_time).total_seconds()
                if checked_count == 1:
                    avg_time = elapsed
                else:
                    avg_time = 0.1 * (elapsed / checked_count) + 0.9 * avg_time
                if checked_count % 500 == 0 or checked_count == total_count:
                    remain = total_count - checked_count
                    secs = avg_time * remain
                    if secs < 60:
                        eta = f"{secs:.0f}s"
                    elif secs < 3600:
                        eta = f"{int(secs//60)}m{int(secs%60)}s"
                    else:
                        eta = f"{int(secs//3600)}h{int(secs%3600//60)}m"
                    logger.info(f"进度: {checked_count}/{total_count} ({checked_count/total_count*100:.1f}%) "
                                f"- 流畅: {len(valid_channels)} - 失败: {failed_count} - ETA: {eta}")

        if success_batch or failed_batch:
            cache_manager.batch_update(successes=tuple(success_batch), failures=tuple(failed_batch))
            success_batch.clear()
            failed_batch.clear()

    valid_channels = sort_channels(valid_channels)
    total_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"完成: 流畅 {len(valid_channels)}/{total_count}, 失败 {failed_count}, 耗时 {int(total_time//60)}m{int(total_time%60)}s")
    cache_manager.save_to_disk()
    return build_m3u(valid_channels)


def iptv_checker(limit: Optional[int] = None) -> bool:
    try:
        iptv_urls_file = get_input_file_path('iptv_urls.txt')
        if not os.path.exists(iptv_urls_file):
            logger.error(f"URL文件不存在: {iptv_urls_file}")
            return False
        with open(iptv_urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        if not urls:
            logger.error("URL文件为空")
            return False
        logger.info(f"读取到 {len(urls)} 个 URL")
        content = _fetch_and_check_channels(urls, limit)
        if content:
            if save_file('playlist.m3u', content):
                logger.info(f"保存完成: {len(parse_m3u(content))} 个频道")
                return True
            logger.error("保存失败")
            return False
        else:
            logger.warning("未发现可用频道")
            return True
    except Exception as e:
        logger.error(f"IPTV检测失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    iptv_checker()
