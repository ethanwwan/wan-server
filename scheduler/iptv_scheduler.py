"""
IPTV 配置定时更新模块

功能：
- 从多个源获取 IPTV 播放列表

"""

import os
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from utils.logger import get_logger
from utils.iptv_utils import (
    fetch_url,
    parse_m3u,
    save_file
)

logger = get_logger('IPTV')

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

# ==================== 主功能函数 ====================

def fetch_migu() -> bool:
    """获取咪咕播放列表"""
    return _fetch_and_save("Migu", CONFIG.iptv.migu_url, 'migu.m3u')


def fetch_ott() -> bool:
    """获取 OTT 播放列表"""
    return _fetch_and_save("OTT", CONFIG.iptv.ott_url, 'ott.m3u')


def fetch_playlist_from_github() -> bool:
    """获取 GitHub 上的播放列表"""
    return _fetch_and_save("GitHub", CONFIG.iptv.playlist_url, 'playlist.m3u')

# ==================== 调度器 ====================

def iptv_scheduler():
    """
    IPTV 配置更新调度器
    
    执行流程：
    1. 获取 Migu 播放列表
    2. 获取 OTT 播放列表
    3. 获取 GitHub 播放列表
    """
    start_time = datetime.now()
    logger.info(f"开始更新配置，时间：{start_time.isoformat()}")
    
    fetch_migu()
    fetch_ott()
    fetch_playlist_from_github()
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"配置更新完成，时间：{end_time.isoformat()}，耗时：{duration:.2f}秒")


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    iptv_scheduler()
