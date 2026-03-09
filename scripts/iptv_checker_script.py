#!/usr/bin/env python3
"""
IPTV 频道检测脚本
用于 GitHub Actions 或命令行直接执行

"""

import os
import sys
from datetime import datetime
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.iptv_utils import save_file, parse_m3u, fetch_channels, build_m3u
from utils.iptv_checker import IPTVChecker
from utils.logger import get_logger

logger = get_logger('IPTV_CHECKER')

IPTV_DIR = os.path.join(project_root, 'output', 'iptv')
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')

# 最大并发数（CPU 友好型）
MAX_WORKERS = min(30, max(10, os.cpu_count() * 2)) if os.cpu_count() else 30

# 全局 IPTV 检测器实例
_iptv_checker = IPTVChecker()

def iptv_checker_job() -> bool:
    """
    IPTV 频道检测任务（使用 GitHub Actions 执行）
    
    Returns:
        bool: 执行是否成功
    """
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")
    
    # 检查配置文件
    if not os.path.exists(IPTV_URLS_FILE):
        logger.error(f"URL 配置文件不存在：{IPTV_URLS_FILE}")
        return False
    
    # 读取 URL 列表
    try:
        with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        logger.error(f"读取 URL 配置文件失败：{e}")
        return False
    
    if not urls:
        logger.error("URL 配置文件为空")
        return False
    
    # 合并频道并检测可用性
    logger.info(f"正在从配置文件获取播放列表，读取到 {len(urls)} 个 URL...")

    # 使用多线程对channels进行检测
    content = fetch_and_check_channels(urls)

    if save_file('playlist.m3u', content):
        channel_count = len(parse_m3u(content))
        logger.info(f"播放列表合并完成，共保存 {channel_count} 个频道")
    else:
        logger.error("保存播放列表失败")
        return False
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{duration:.2f}秒")
    
    return True

def fetch_and_check_channels(urls: List[str]) -> str:
    """
    从 URL 列表获取并检查频道可用性
    
    Args:
        urls: URL 列表
        
    Returns:
        可用的 M3U 频道列表
    """
    # 1. 获取所有频道
    all_channels = fetch_channels(urls, max_workers=MAX_WORKERS)
    
    if not all_channels:
        logger.warning("未获取到任何频道")
        return ''
    
    logger.info(f"获取到 {len(all_channels)} 个频道，开始检测可用性...")
    
    # 2. 检测频道可用性
    valid_channels = []
    total_count = len(all_channels)
    checked_count = 0
    
    def check_single_channel(channel):
        """检测单个频道"""
        url = channel.get('url', '')
        name = channel.get('channel_name', '')
        
        try:
            result = _iptv_checker.check(url)
            return (channel, result)
        except Exception as e:
            logger.error(f"检测异常 [{name}]: {e}")
            return (channel, {'available': False, 'fluent': False, 'error': str(e)})
    
    # 使用多线程并发检测
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {executor.submit(check_single_channel, ch): ch for ch in all_channels}
        
        for future in as_completed(future_to_channel):
            channel, result = future.result()
            
            # 只有通过检测的频道才保留
            if result.get('available') and result.get('fluent'):
                # 添加 fps 和 bitrate 信息
                channel['fps'] = result.get('fps')
                channel['bitrate'] = result.get('bitrate')
                valid_channels.append(channel)
            
            checked_count += 1
            
            # 每 500 个打印一次进度
            if checked_count % 500 == 0 or checked_count == total_count:
                progress = checked_count / total_count * 100
                logger.info(f"检测进度: {checked_count}/{total_count} ({progress:.1f}%) - 可用: {len(valid_channels)}")
    
    logger.info(f"检测完成，可用频道: {len(valid_channels)}/{total_count}")
    
    # 3. 构建 M3U 内容
    return build_m3u(valid_channels)

def main():
    """主入口函数"""
    logger.info("=" * 60)
    logger.info("开始执行 IPTV 配置更新任务")
    logger.info("=" * 60)
    
    try:
        success = iptv_checker_job()
        
        logger.info("=" * 60)
        if success:
            logger.info("✅ IPTV 配置更新任务执行成功")
        else:
            logger.error("❌ IPTV 配置更新任务执行失败")
        logger.info("=" * 60)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ 任务执行失败：{e}", exc_info=True)
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
