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
import re
from collections import defaultdict, Counter

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.iptv_utils import parse_m3u, classify_channels, sort_channels


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
    optimized_channels = classify_channels(channels, keep_unmatched=False)
    optimized_channels = sort_channels(optimized_channels)
    
    # 统计分类结果
    total_channels = len(channels)
    valid_channels = len(optimized_channels)
    filtered_count = total_channels - valid_channels
    
    # 按 group_title 分组统计（保持原始顺序）
    groups = defaultdict(list)
    seen_groups = []
    for ch in optimized_channels:
        group = ch.get('group_title', '')
        groups[group].append(ch)
        if group not in seen_groups:
            seen_groups.append(group)
    
    print(seen_groups)

    print(f"\n{'=' * 80}")
    print("📊 分组统计结果")
    print(f"{'=' * 80}")
    print(f"   总频道数：{total_channels} 个")
    print(f"   过滤掉的频道：{filtered_count} 个")
    print(f"   有效频道数：{valid_channels} 个")
    print(f"   分类后分组数：{len(groups)} 个")
    
    print(f"\n{'=' * 80}")
    print("📋 分类后的分组结果")
    print(f"{'=' * 80}")
    
    # 打印所有分组及其频道（去重，按原始顺序）
    for category in seen_groups:
        chs = groups[category]
        print(f"\n{category} ({len(chs)} 个频道)")
        print("-" * 40)
        seen_names = set()
        for ch in chs:
            name = ch.get('channel_name', 'Unknown')
            if name not in seen_names:
                seen_names.add(name)
                print(f"  - {name}")
    
    # 保存到文件
    report_file = os.path.join(project_root, 'output', 'iptv', 'group_analysis_report.txt')
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("IPTV 分组分析报告\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("📊 分组统计结果\n")
        f.write("=" * 80 + "\n")
        f.write(f"   总频道数：{total_channels} 个\n")
        f.write(f"   过滤掉的频道：{filtered_count} 个\n")
        f.write(f"   有效频道数：{valid_channels} 个\n")
        f.write(f"   分类后分组数：{len(groups)} 个\n")
        
        f.write("\n\n📋 分类后的分组结果\n")
        f.write("=" * 80 + "\n")
        
        for category in seen_groups:
            chs = groups[category]
            f.write(f"\n{category} ({len(chs)} 个频道)\n")
            f.write("-" * 40 + "\n")
            seen_names = set()
            for ch in chs:
                name = ch.get('channel_name', 'Unknown')
                if name not in seen_names:
                    seen_names.add(name)
                    f.write(f"  - {name}\n")
    
    print(f"\n✅ 报告已保存到：{report_file}")
    print(f"\n✅ 分组优化完成，保留 {valid_channels} 个频道")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
