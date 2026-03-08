#!/usr/bin/env python3
"""
IPTV 频道检测脚本
用于 GitHub Actions 或命令行直接执行

"""

import os
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.iptv_utils import save_file, parse_m3u, merge_channels
from utils.logger import get_logger

logger = get_logger('IPTV_CHECKER')

# 常量配置
IPTV_DIR = os.path.join(project_root, 'output', 'iptv')
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')


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
    content = merge_channels(urls)
    
    # 保存结果
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



if __name__ == "__main__":
    print("=" * 60)
    print("开始执行 IPTV 配置更新任务")
    print("=" * 60)
    
    try:
        iptv_checker_job()
        print("\n" + "=" * 60)
        print("IPTV 配置更新任务执行完成")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 任务执行失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
