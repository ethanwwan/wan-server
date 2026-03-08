#!/usr/bin/env python3
"""
IPTV URL 分析测试脚本

功能：
- 读取 input/iptv_urls.txt 中的所有 URL
- 逐个分析每个 URL 的内容
- 统计频道数量、分类、URL 特色等
- 生成详细的分析报告

使用方式:
    python scripts/analyze_iptv_urls.py
"""

import os
import sys
import re
from collections import Counter, defaultdict
from typing import List, Dict, Any
from urllib.parse import urlparse

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.iptv_utils import fetch_url, parse_m3u, parse_txt
from utils.logger import get_logger

logger = get_logger('IPTV_ANALYZER')

# 常量配置
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')


def analyze_url(url: str) -> Dict[str, Any]:
    """
    分析单个 URL
    
    Args:
        url: 要分析的 URL
    
    Returns:
        包含分析结果的字典
    """
    result = {
        'url': url,
        'success': False,
        'error': None,
        'channels': [],
        'channel_count': 0,
        'groups': {},
        'url_patterns': {},
        'protocols': {},
        'file_type': 'unknown'
    }
    
    try:
        # 获取内容
        content = fetch_url(url)
        if not content:
            result['error'] = '获取内容为空'
            return result
        
        # 判断文件类型并解析
        if url.endswith('.txt'):
            result['file_type'] = 'txt'
            channels = parse_txt(content)
        else:
            result['file_type'] = 'm3u'
            channels = parse_m3u(content)
        
        result['channels'] = channels
        result['channel_count'] = len(channels)
        result['success'] = True
        
        # 分析频道分组
        group_counter = Counter()
        for ch in channels:
            group = ch.group_title or '未分类'
            group_counter[group] += 1
        result['groups'] = dict(group_counter)
        
        # 分析 URL 特征
        protocol_counter = Counter()
        domain_counter = Counter()
        extension_counter = Counter()
        
        for ch in channels:
            # 协议分析
            if ch.url.startswith('http://'):
                protocol_counter['HTTP'] += 1
            elif ch.url.startswith('https://'):
                protocol_counter['HTTPS'] += 1
            elif ch.url.startswith('rtmp://'):
                protocol_counter['RTMP'] += 1
            elif ch.url.startswith('rtsp://'):
                protocol_counter['RTSP'] += 1
            elif ch.url.startswith('rtp://'):
                protocol_counter['RTP'] += 1
            else:
                protocol_counter['OTHER'] += 1
            
            # 域名分析
            try:
                parsed = urlparse(ch.url)
                domain = parsed.netloc
                domain_counter[domain] += 1
            except:
                pass
            
            # 扩展名分析
            if '.m3u8' in ch.url:
                extension_counter['HLS (.m3u8)'] += 1
            elif '.mp4' in ch.url:
                extension_counter['MP4'] += 1
            elif '.ts' in ch.url:
                extension_counter['MPEG-TS'] += 1
            elif '.flv' in ch.url:
                extension_counter['FLV'] += 1
            else:
                extension_counter['OTHER'] += 1
        
        result['url_patterns'] = {
            'protocols': dict(protocol_counter),
            'domains': dict(domain_counter.most_common(10)),  # 前 10 个域名
            'extensions': dict(extension_counter)
        }
        
        # 频道名称分析
        name_patterns = Counter()
        for ch in channels:
            name = ch.channel_name
            if 'CCTV' in name.upper():
                name_patterns['央视'] += 1
            elif '卫视' in name or '卫视' in name.upper():
                name_patterns['卫视'] += 1
            elif '地方' in name or any(city in name.upper() for city in ['BEIJING', 'SHANGHAI', 'GUANGDONG']):
                name_patterns['地方台'] += 1
            else:
                name_patterns['其他'] += 1
        
        result['channel_types'] = dict(name_patterns)
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def print_analysis_report(results: List[Dict[str, Any]]):
    """
    打印分析报告
    
    Args:
        results: 分析结果列表
    """
    print("\n" + "=" * 80)
    print(" " * 30 + "IPTV URL 分析报告")
    print("=" * 80)
    
    total_channels = 0
    success_count = 0
    
    for i, result in enumerate(results, 1):
        print(f"\n{'=' * 80}")
        print(f"URL #{i}: {result['url']}")
        print(f"{'=' * 80}")
        
        if not result['success']:
            print(f"❌ 分析失败：{result['error']}")
            continue
        
        success_count += 1
        total_channels += result['channel_count']
        
        # 基本信息
        print(f"\n📊 基本信息:")
        print(f"   文件类型：{result['file_type'].upper()}")
        print(f"   频道总数：{result['channel_count']} 个")
        print(f"   分析状态：✅ 成功")
        
        # 频道分组统计
        if result['groups']:
            print(f"\n📁 频道分组统计:")
            sorted_groups = sorted(result['groups'].items(), key=lambda x: x[1], reverse=True)
            for group, count in sorted_groups[:10]:  # 显示前 10 个分组
                percentage = (count / result['channel_count']) * 100
                bar = '█' * int(percentage / 2)
                print(f"   {group:20s} {bar:25s} {count:4d} 个 ({percentage:5.1f}%)")
            
            if len(result['groups']) > 10:
                print(f"   ... 还有 {len(result['groups']) - 10} 个分组")
        
        # 频道类型统计
        if result.get('channel_types'):
            print(f"\n📺 频道类型统计:")
            for ch_type, count in result['channel_types'].items():
                percentage = (count / result['channel_count']) * 100
                print(f"   {ch_type:15s} {count:4d} 个 ({percentage:5.1f}%)")
        
        # URL 协议分析
        if result['url_patterns']['protocols']:
            print(f"\n🔗 传输协议分析:")
            for protocol, count in result['url_patterns']['protocols'].items():
                percentage = (count / result['channel_count']) * 100
                print(f"   {protocol:15s} {count:4d} 个 ({percentage:5.1f}%)")
        
        # URL 扩展名分析
        if result['url_patterns']['extensions']:
            print(f"\n📄 流媒体格式分析:")
            for ext, count in result['url_patterns']['extensions'].items():
                percentage = (count / result['channel_count']) * 100
                print(f"   {ext:15s} {count:4d} 个 ({percentage:5.1f}%)")
        
        # 域名分析
        if result['url_patterns']['domains']:
            print(f"\n🌐 主要域名分布 (Top 10):")
            for domain, count in result['url_patterns']['domains'].items():
                percentage = (count / result['channel_count']) * 100
                print(f"   {domain:40s} {count:4d} 个 ({percentage:5.1f}%)")
        
        # 特色分析
        print(f"\n💡 URL 特色分析:")
        
        # 判断是否有特殊域名
        domains = result['url_patterns']['domains']
        if any('github' in d.lower() for d in domains.keys()):
            print(f"   ✓ 使用 GitHub 作为源")
        if any('gh-proxy' in d.lower() for d in domains.keys()):
            print(f"   ✓ 使用 GitHub 代理加速")
        if any('migu' in d.lower() for d in domains.keys()):
            print(f"   ✓ 包含咪咕视频源")
        if any('ott' in d.lower() for d in domains.keys()):
            print(f"   ✓ 包含 OTT 视频源")
        
        # 协议特色
        protocols = result['url_patterns']['protocols']
        if protocols.get('HTTPS', 0) > protocols.get('HTTP', 0):
            print(f"   ✓ 主要使用 HTTPS 加密传输")
        if protocols.get('RTMP', 0) > 0 or protocols.get('RTSP', 0) > 0:
            print(f"   ✓ 包含实时流媒体协议 (RTMP/RTSP)")
        
        # 格式特色
        extensions = result['url_patterns']['extensions']
        if extensions.get('HLS (.m3u8)', 0) > result['channel_count'] * 0.5:
            print(f"   ✓ 主要使用 HLS 流媒体格式")
        
        # 频道特色
        channel_types = result.get('channel_types', {})
        if channel_types.get('央视', 0) > 0:
            print(f"   ✓ 包含央视频道")
        if channel_types.get('卫视', 0) > 0:
            print(f"   ✓ 包含卫视频道")
        
        # 质量评估
        print(f"\n⭐ 质量评估:")
        quality_score = 0
        
        # HTTPS 比例高加分
        https_ratio = protocols.get('HTTPS', 0) / result['channel_count'] if result['channel_count'] > 0 else 0
        if https_ratio > 0.8:
            quality_score += 3
            print(f"   ✓ HTTPS 覆盖率高 ({https_ratio*100:.1f}%)")
        elif https_ratio > 0.5:
            quality_score += 2
            print(f"   ✓ HTTPS 覆盖率中等 ({https_ratio*100:.1f}%)")
        
        # 有分组信息加分
        if len(result['groups']) > 5:
            quality_score += 2
            print(f"   ✓ 频道分组完善 ({len(result['groups'])} 个分组)")
        
        # HLS 格式加分
        hls_ratio = extensions.get('HLS (.m3u8)', 0) / result['channel_count'] if result['channel_count'] > 0 else 0
        if hls_ratio > 0.7:
            quality_score += 2
            print(f"   ✓ 主要使用 HLS 格式 ({hls_ratio*100:.1f}%)")
        
        # 频道数量加分
        if result['channel_count'] > 500:
            quality_score += 2
            print(f"   ✓ 频道数量丰富 ({result['channel_count']} 个)")
        elif result['channel_count'] > 100:
            quality_score += 1
            print(f"   ✓ 频道数量适中 ({result['channel_count']} 个)")
        
        # 总体评分
        print(f"\n   综合评分：{'⭐' * quality_score} ({quality_score}/10)")
    
    # 总结
    print(f"\n{'=' * 80}")
    print("📋 总体统计:")
    print(f"{'=' * 80}")
    print(f"   总 URL 数：{len(results)} 个")
    print(f"   成功分析：{success_count} 个")
    print(f"   分析失败：{len(results) - success_count} 个")
    print(f"   总频道数：{total_channels} 个")
    
    if success_count > 0:
        avg_channels = total_channels / success_count
        print(f"   平均每个 URL: {avg_channels:.1f} 个频道")
    
    print(f"{'=' * 80}\n")


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print(" " * 25 + "IPTV URL 分析测试脚本")
    print("=" * 80)
    
    # 检查文件是否存在
    if not os.path.exists(IPTV_URLS_FILE):
        logger.error(f"URL 配置文件不存在：{IPTV_URLS_FILE}")
        sys.exit(1)
    
    # 读取 URL 列表
    try:
        with open(IPTV_URLS_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        logger.error(f"读取 URL 配置文件失败：{e}")
        sys.exit(1)
    
    if not urls:
        logger.error("URL 配置文件为空")
        sys.exit(1)
    
    print(f"\n📝 读取到 {len(urls)} 个 URL，开始分析...\n")
    
    # 逐个分析
    results = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] 正在分析：{url}")
        result = analyze_url(url)
        results.append(result)
        
        if result['success']:
            print(f"  ✅ 完成，共 {result['channel_count']} 个频道")
        else:
            print(f"  ❌ 失败：{result['error']}")
    
    # 打印报告
    print_analysis_report(results)
    
    # 保存报告到文件
    report_file = os.path.join(project_root, 'output', 'iptv', 'analysis_report.txt')
    try:
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            # 简单保存文本报告
            f.write("IPTV URL 分析报告\n")
            f.write("=" * 80 + "\n\n")
            for i, result in enumerate(results, 1):
                f.write(f"URL #{i}: {result['url']}\n")
                f.write(f"状态：{'成功' if result['success'] else '失败'}\n")
                if result['success']:
                    f.write(f"频道数：{result['channel_count']}\n")
                    f.write(f"分组数：{len(result['groups'])}\n")
                f.write("\n")
        
        logger.info(f"报告已保存到：{report_file}")
    except Exception as e:
        logger.error(f"保存报告失败：{e}")


if __name__ == "__main__":
    main()
