#!/usr/bin/env python3
"""
IPTV 分组分析脚本

功能：
- 读取 playlist.m3u 文件
- 提取所有频道的 group-title 和频道名
- 分析原始分组，将类似的分组进行合并
- 打印分组前后的对比情况
"""

import os
import sys
from collections import defaultdict

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.iptv_utils import parse_m3u, classify_channels


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print(" " * 30 + "IPTV 分组分析脚本")
    print("=" * 80)
    
    # 读取 playlist.m3u 文件
    m3u_file = os.path.join(project_root, 'output', 'iptv', 'playlist.m3u')
    if not os.path.exists(m3u_file):
        print(f"❌ M3U 文件不存在：{m3u_file}")
        sys.exit(1)
    
    # 解析频道
    try:
        with open(m3u_file, 'r', encoding='utf-8') as f:
            content = f.read()
        channels = parse_m3u(content)
    except Exception as e:
        print(f"❌ 解析 M3U 文件失败：{e}")
        sys.exit(1)
    
    if not channels:
        print("❌ M3U 文件中没有频道")
        sys.exit(1)
    
    print(f"\n📊 读取到 {len(channels)} 个频道，开始分析...\n")
    
    # 对频道进行分组优化
    optimized_channels = classify_channels(channels)
    
    # 统计分类结果
    total_channels = len(channels)
    valid_channels = len(optimized_channels)
    filtered_count = total_channels - valid_channels
    
    # 按 group_title 分组统计
    groups = defaultdict(list)
    for ch in optimized_channels:
        group = ch.get('group_title', '')
        groups[group].append(ch)
    
    print(f"\n{'=' * 80}")
    print("📊 分组统计结果")
    print(f"{'=' * 80}")
    print(f"   总频道数：{total_channels} 个")
    print(f"   过滤掉的频道：{filtered_count} 个")
    print(f"   有效频道数：{valid_channels} 个")
    print(f"   分类后分组数：{len(groups)} 个")
    
    print(f"\n{'=' * 80}")
    print("📋 分类后的分组结果（按频道数排序）")
    print(f"{'=' * 80}")
    
    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
    for i, (category, chs) in enumerate(sorted_groups, 1):
        print(f"{i:3d}. {category:50s} {len(chs):4d} 个频道")
        print()
    
    print(f"\n✅ 分组优化完成，保留 {valid_channels} 个频道")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
