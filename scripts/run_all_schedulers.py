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
from typing import List, Callable, Tuple

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.logger import get_logger

logger = get_logger('SCHEDULERS')


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


def iptv_job() -> bool:
    """执行 IPTV 频道检测任务"""
    try:
        from scheduler.iptv_scheduler import iptv_scheduler
        return iptv_scheduler()
    except Exception as e:
        logger.error(f"IPTV 频道检测失败: {e}", exc_info=True)
        return False


def run_task(task_name: str, task_func: Callable[[], bool]) -> bool:
    """通用任务执行包装器"""
    logger.info("=" * 60)
    logger.info(f"开始执行 {task_name} 任务")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    success = task_func()
    duration = (datetime.now() - start_time).total_seconds()
    
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds:.2f}秒"
    
    status = "✅ 成功" if success else "❌ 失败"
    logger.info(f"{task_name} 任务完成: {status}，耗时: {time_str}")
    
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
        ("Singbox", singbox_job),
        ("TVBox", tvbox_job),
        ("IPTV", iptv_job),
    ]
    
    # 执行所有任务
    results = [(name, run_task(name, func)) for name, func in tasks]
    
    # 输出汇总
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    total_time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds:.2f}秒"
    
    logger.info("=" * 80)
    logger.info(" " * 25 + "调度任务执行结果汇总")
    logger.info("=" * 80)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"   {name}: {status}")
    
    logger.info(f"\n   成功数: {success_count}")
    logger.info(f"   失败数: {total_count - success_count}")
    logger.info(f"   总耗时: {total_time_str}")
    logger.info(f"   结束时间: {end_time.isoformat()}")
    logger.info("=" * 80)
    
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()