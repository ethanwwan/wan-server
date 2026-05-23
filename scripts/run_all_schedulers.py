#!/usr/bin/env python3
"""
统一调度脚本

功能：
1. Singbox 配置更新
2. TVBox 配置更新  
3. IPTV 频道检测

使用方式:
    python scripts/run_all_schedulers.py
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Callable, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 核心导入（避免循环导入问题）
from utils.iptv_utils import save_file, parse_m3u, fetch_channels, build_m3u, sort_channels
from utils.iptv_checker import IPTVChecker
from utils.logger import get_logger

logger = get_logger('SCHEDULERS')

# 配置常量
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')
MAX_WORKERS = min(30, max(10, os.cpu_count() * 2)) if os.cpu_count() else 30

# 全局 IPTV 检测器实例（复用）
_iptv_checker = IPTVChecker()


def fetch_and_check_channels(urls: List[str], limit: Optional[int] = None) -> str:
    """从 URL 列表获取并检查频道可用性"""
    all_channels = fetch_channels(urls, max_workers=MAX_WORKERS, limit=limit)
    
    if not all_channels:
        logger.warning("未获取到任何频道")
        return ''
    
    logger.info(f"开始检测 {len(all_channels)} 个频道的可用性...")
    
    valid_channels = []
    total_count = len(all_channels)
    checked_count = 0
    start_time = datetime.now()
    
    # 指数加权平均参数
    alpha = 0.1  # 平滑系数，越小越平滑
    avg_time_per_channel = 0.0  # 加权平均时间
    
    def check_single_channel(channel: Dict) -> Tuple[Dict, Dict]:
        url = channel.get('url', '')
        name = channel.get('channel_name', '')
        try:
            result = _iptv_checker.check(url)
            return (channel, result)
        except Exception as e:
            logger.error(f"检测异常 [{name}]: {e}")
            return (channel, {'available': False, 'fluent': False, 'error': str(e)})
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {executor.submit(check_single_channel, ch): ch for ch in all_channels}
        
        for future in as_completed(future_to_channel):
            channel, result = future.result()
            if result.get('available'):
                valid_channels.append(channel)
            
            checked_count += 1
            
            # 更新指数加权平均
            current_elapsed = (datetime.now() - start_time).total_seconds()
            if checked_count == 1:
                avg_time_per_channel = current_elapsed
            else:
                # 指数加权平均：给近期数据更高权重
                instant_time = current_elapsed / checked_count
                avg_time_per_channel = alpha * instant_time + (1 - alpha) * avg_time_per_channel
            
            if checked_count % 500 == 0 or checked_count == total_count:
                progress = checked_count / total_count * 100
                
                # 使用加权平均计算剩余时间
                remaining_channels = total_count - checked_count
                remaining_seconds = avg_time_per_channel * remaining_channels
                
                # 格式化剩余时间
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
    
    valid_channels = sort_channels(valid_channels)
    total_time = (datetime.now() - start_time).total_seconds()
    
    # 格式化耗时为 x分x秒
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    time_str = f"{minutes}分{seconds}秒"
    
    logger.info(f"检测完成，可用频道: {len(valid_channels)}/{total_count}，总耗时: {time_str}")
    
    return build_m3u(valid_channels)


def iptv_checker_job(limit: Optional[int] = None) -> bool:
    """IPTV 频道检测任务"""
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
        content = fetch_and_check_channels(urls, limit)
        
        if content:
            if save_file('playlist.m3u', content):
                channel_count = len(parse_m3u(content))
                logger.info(f"播放列表合并完成，共保存 {channel_count} 个频道")
                return True
            logger.error("保存播放列表失败")
            return False
        else:
            # 降级处理：检测结果为0，保留上次的播放列表
            logger.warning("本次检测未发现可用频道，保留上次的播放列表")
            return True
        
    except Exception as e:
        logger.error(f"IPTV 频道检测失败: {e}", exc_info=True)
        return False


def singbox_job() -> bool:
    """执行 Singbox 配置更新任务"""
    try:
        from scheduler.singbox_scheduler import singbox_scheduler
        singbox_scheduler()
        return True
    except Exception as e:
        logger.error(f"Singbox 配置更新失败: {e}", exc_info=True)
        return False


def tvbox_job() -> bool:
    """执行 TVBox 配置更新任务"""
    try:
        from scheduler.tvbox_scheduler import tvbox_scheduler
        tvbox_scheduler()
        return True
    except Exception as e:
        logger.error(f"TVBox 配置更新失败: {e}", exc_info=True)
        return False


def run_task(task_name: str, task_func: Callable[[], bool]) -> bool:
    """通用任务执行包装器"""
    logger.info("=" * 60)
    logger.info(f"开始执行 {task_name} 任务")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    success = task_func()
    duration = (datetime.now() - start_time).total_seconds()
    
    status = "✅ 成功" if success else "❌ 失败"
    logger.info(f"{task_name} 任务完成: {status}，耗时: {duration:.2f}秒")
    
    return success


def main():
    """主入口函数"""
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info(" " * 25 + "统一调度任务开始")
    logger.info("=" * 80)
    logger.info(f"开始时间: {start_time.isoformat()}")
    
    # 任务配置列表（按执行顺序）
    tasks: List[Tuple[str, Callable[[], bool]]] = [
        # ("Singbox", singbox_job),
        ("TVBox", tvbox_job),
        ("IPTV", iptv_checker_job),
    ]
    
    # 执行所有任务
    results = [(name, run_task(name, func)) for name, func in tasks]
    
    # 输出汇总
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("=" * 80)
    logger.info(" " * 25 + "调度任务执行结果汇总")
    logger.info("=" * 80)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"   {name}: {status}")
    
    logger.info(f"\n   总任务数: {total_count}")
    logger.info(f"   成功数: {success_count}")
    logger.info(f"   失败数: {total_count - success_count}")
    logger.info(f"   总耗时: {duration:.2f}秒")
    logger.info(f"   结束时间: {end_time.isoformat()}")
    logger.info("=" * 80)
    
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()
