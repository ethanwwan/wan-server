#!/usr/bin/env python3
"""
IPTV 调度任务独立运行脚本
用于 GitHub Actions 或命令行直接执行
"""

import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scheduler.iptv_scheduler import iptv_scheduler_fetch_playlist

if __name__ == "__main__":
    print("=" * 60)
    print("开始执行 IPTV 配置更新任务")
    print("=" * 60)
    
    try:
        iptv_scheduler_fetch_playlist()
        print("\n" + "=" * 60)
        print("IPTV 配置更新任务执行完成")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 任务执行失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
