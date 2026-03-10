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

from utils.iptv_utils import fetch_url, parse_m3u, parse_txt, build_m3u, save_file
from utils.logger import get_logger

logger = get_logger('IPTV_ANALYZER')

# 常量配置
IPTV_URLS_FILE = os.path.join(project_root, 'input', 'iptv_urls.txt')


def analyze_channels(channels: List[Dict]) -> Dict[str, Any]:
    """
    分析频道列表
    
    Args:
        channels: 频道字典列表
        
    Returns:
        分析结果字典
    """
    result = {
        'channel_count': len(channels),
        'groups': {},
        'url_patterns': {},
        'channel_types': {},
        'success': True
    }
    
    # 频道分组统计
    group_counter = Counter()
    for ch in channels:
        group = ch.get('group_title', '未分组')
        if group:
            group_counter[group] += 1
    result['groups'] = dict(group_counter)
    
    # URL 分析
    protocol_counter = Counter()
    domain_counter = Counter()
    extension_counter = Counter()
    
    for ch in channels:
        url = ch.get('url', '')
        if not url:
            continue
        
        # 协议
        if url.startswith('https://'):
            protocol_counter['HTTPS'] += 1
        elif url.startswith('http://'):
            protocol_counter['HTTP'] += 1
        elif url.startswith('rtmp://'):
            protocol_counter['RTMP'] += 1
        elif url.startswith('rtsp://'):
            protocol_counter['RTSP'] += 1
        else:
            protocol_counter['OTHER'] += 1
        
        # 域名
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            domain_counter[domain] += 1
        except:
            pass
        
        # 扩展名
        if '.m3u8' in url:
            extension_counter['HLS (.m3u8)'] += 1
        elif '.mp4' in url:
            extension_counter['MP4'] += 1
        elif '.flv' in url:
            extension_counter['FLV'] += 1
        else:
            extension_counter['OTHER'] += 1
    
    result['url_patterns'] = {
        'protocols': dict(protocol_counter),
        'domains': dict(domain_counter.most_common(10)),
        'extensions': dict(extension_counter)
    }
    
    # 频道类型统计
    type_counter = Counter()
    for ch in channels:
        name = ch.get('channel_name', '').upper()
        if 'CCTV' in name:
            type_counter['央视'] += 1
        elif '卫视' in name or '省级' in name:
            type_counter['卫视'] += 1
        elif '教育' in name or '科教' in name:
            type_counter['教育'] += 1
        elif '电影' in name or '影院' in name:
            type_counter['电影'] += 1
        elif '体育' in name:
            type_counter['体育'] += 1
        elif '新闻' in name:
            type_counter['新闻'] += 1
        elif '少儿' in name or '卡通' in name:
            type_counter['少儿'] += 1
        elif '国际' in name:
            type_counter['国际'] += 1
        else:
            type_counter['其他'] += 1
    
    result['channel_types'] = dict(type_counter)
    
    return result


def print_channel_analysis_report(result: Dict[str, Any]):
    """
    打印频道分析报告
    
    Args:
        result: 分析结果字典
    """
    print("\n" + "=" * 80)
    print(" " * 30 + "IPTV 频道分析报告")
    print("=" * 80)
    
    if not result['success']:
        print(f"❌ 分析失败")
        return
    
    total_channels = result['channel_count']
    
    print(f"\n📊 基本信息:")
    print(f"   频道总数：{total_channels} 个")
    print(f"   分析状态：✅ 成功")
    
    # 频道分组统计
    if result['groups']:
        print(f"\n📁 频道分组统计:")
        sorted_groups = sorted(result['groups'].items(), key=lambda x: x[1], reverse=True)
        for group, count in sorted_groups:
            percentage = (count / total_channels) * 100
            bar = '█' * int(percentage / 2)
            print(f"   {group:20s} {bar:25s} {count:4d} 个 ({percentage:5.1f}%)")
    
    # 频道类型统计
    if result.get('channel_types'):
        print(f"\n📺 频道类型统计:")
        for ch_type, count in result['channel_types'].items():
            percentage = (count / total_channels) * 100
            print(f"   {ch_type:15s} {count:4d} 个 ({percentage:5.1f}%)")
    
    # URL 协议分析
    url_patterns = result.get('url_patterns', {})
    if url_patterns.get('protocols'):
        print(f"\n🔗 传输协议分析:")
        for protocol, count in url_patterns['protocols'].items():
            percentage = (count / total_channels) * 100
            print(f"   {protocol:15s} {count:4d} 个 ({percentage:5.1f}%)")
    
    # URL 扩展名分析
    if url_patterns.get('extensions'):
        print(f"\n📄 流媒体格式分析:")
        for ext, count in url_patterns['extensions'].items():
            percentage = (count / total_channels) * 100
            print(f"   {ext:15s} {count:4d} 个 ({percentage:5.1f}%)")
    
    # 域名分析
    if url_patterns.get('domains'):
        print(f"\n🌐 主要域名分布 (Top 10):")
        for domain, count in url_patterns['domains'].items():
            percentage = (count / total_channels) * 100
            print(f"   {domain:40s} {count:4d} 个 ({percentage:5.1f}%)")
    
    # 特色分析
    print(f"\n💡 URL 特色分析:")
    
    # 判断是否有特殊域名
    domains = url_patterns.get('domains', {})
    if any('github' in d.lower() for d in domains.keys()):
        print(f"   ✓ 使用 GitHub 作为源")
    if any('gh-proxy' in d.lower() for d in domains.keys()):
        print(f"   ✓ 使用 GitHub 代理加速")
    if any('migu' in d.lower() for d in domains.keys()):
        print(f"   ✓ 包含咪咕视频源")
    if any('ott' in d.lower() for d in domains.keys()):
        print(f"   ✓ 包含 OTT 视频源")
    
    # 协议特色
    protocols = url_patterns.get('protocols', {})
    if protocols.get('HTTPS', 0) > protocols.get('HTTP', 0):
        print(f"   ✓ 主要使用 HTTPS 加密传输")
    if protocols.get('RTMP', 0) > 0 or protocols.get('RTSP', 0) > 0:
        print(f"   ✓ 包含实时流媒体协议 (RTMP/RTSP)")
    
    # 格式特色
    extensions = url_patterns.get('extensions', {})
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
    print(f"   总频道数：{total_channels} 个")
    print(f"{'=' * 80}\n")


# 提前过滤掉一些不需要的group_title
exclude_groups = ['🎤周杰伦歌曲点播', '🎹歌手合集点播', '🎞️电影直播']

def reclassify_and_save(channels: List[Dict]):
    """
    对频道进行重新分类和整理，并保存到 M3U 文件
    
    Args:
        channels: 频道字典列表
        output_file: 输出文件路径，默认为 output/iptv/temp.m3u
    """
    # 重新分类逻辑
    reclassified = []

    # 按频道名称关键词重新分类
    category_map = {
        '央视': ['CCTV', '央视', '中央', 'CGTN', 'IPANDA', '熊猫频道', '汉语文化'],
        '卫视': ['卫视', '省级', '东南', '东方', '南方', '北方'],
        '地方台': ['北京', '上海', '广东', '浙江', '江苏', '湖南', '湖北', '四川', '重庆', '天津', '河北', '河南', '山东', '山西', '陕西', '江西', '福建', '安徽', '贵州', '云南', '广西', '海南', '黑龙江', '吉林', '辽宁', '内蒙古', '宁夏', '新疆', '青海', '甘肃', '西藏', '地方', '广州', '佛山', '江门', '汕头', '深圳', '珠海', '东莞', '中山', '惠州', '肇庆', '清远', '韶关', '河源', '梅州', '汕尾', '揭阳', '阳江', '茂名', '湛江', '潮州', '云浮', '顺德', '南海', '番禺', '增城', '从化', '乐昌', '南雄', '仁化', '始兴', '翁源', '新丰', '乳源', '曲江', '武江', '浈江', '高州', '化州', '信宜', '电白', '吴川', '廉江', '雷州', '徐闻', '遂溪', '广宁', '德庆', '封开', '怀集', '高要', '四会', '恩平', '开平', '台山', '鹤山', '新会', '阳春', '阳西', '阳东', '连州', '连南', '连山', '阳山', '佛冈', '英德', '清新', '清城', '南宁', '南京', '宁波', '杭州', '邢台', '绍兴', '上虞', '嵊泗', '湖州', '泉州', '厦门', '福州', '漳州', '龙岩', '三明', '南平', '宁德', '莆田', '泉州', '晋江', '石狮', '南安', '安溪', '永春', '德化', '惠安', '泉港', '洛江', '台商', '开发区', 'QTV'],
        '电影': ['电影', '影院', 'MOVIE', 'FILM', '动作', '喜剧', '爱情', '科幻', '恐怖', '悬疑', '经典', '影剧', '剧场', '影视', '热播剧场', '哈利波特', '笑傲江湖', '西游记', 'A 计划'],
        '体育': ['体育', 'SPORT', 'PLU', '五星体育', 'NBA', 'CBA', '英超', '西甲', '德甲', '意甲', '法甲', '欧冠', '亚冠', '中超', '足球', '篮球', '排球', '乒乓球', '羽毛球', '网球', '高尔夫', '赛车', 'F1', 'UFC', '格斗', '咪咕赛事', '咪咕体育', '咪视界', '蜘蛛直播', '半决赛', '决赛', '锦标赛', '公开赛', '咪咕', '咪视通', 'Big3'],
        '新闻': ['新闻', 'NEWS', '资讯', '时事', '报道', '直播'],
        '财经': ['财经', 'FINANCE', '经济', '股票', '证券', '金融', 'BLOOMBERG', '彭博'],
        '科教': ['科教', '教育', 'CETV', '学习', '课堂', '教学', '讲座', '法治天地', '教科'],
        '少儿': ['少儿', '动画', '卡通', '动漫', 'CHILD', 'KIDS', '亲子', '儿歌', '童话', '儿童', '卡通动画', '少儿教育', '哈哈炫动'],
        '综艺': ['综艺', '娱乐', 'MUSIC', '戏剧', '戏曲', '音乐', '歌舞', '明星', '演唱会', '脱口秀', '真人秀', '春晚', '晚会', '歌手', 'K 歌', '点歌', '锋味', '快乐垂钓', '手游', '游戏', '端游', '美女展示', 'MUZZIK'],
        '国际': ['国际', 'WORLD', 'CNN', 'BBC', 'PHOENIX', 'STAR', 'HBO', '国家地理', '探索', 'DISCOVERY', 'NATGEO', 'NHK', 'KBS', 'TVB', 'flix', '翡翠台', '澳视', '澳门', '澳亚', 'ABC', 'CBS', 'NBC', 'CNA', 'AL JAZEERA', 'PENTHOUSE', 'XXX', 'GEO', 'SERBIA', 'CMT', 'AXS', 'COMEDY', 'AUTENTIC', 'CSPAN', 'ACTION', 'ADVENTURE', 'CARTOON', 'CLARITY', 'MONTV', 'ANDOR'],
        '纪录片': ['纪录', 'DOCUMENTARY', 'NATGEO', 'DISCOVERY', '人文', '历史', '地理', '自然', '生物', '金鹰纪实', '睛彩'],
        '生活': ['生活', '健康', '旅游', '美食', '时尚', '家居', '购物', '养生', '菜谱', '装修', '垂钓', '钓鱼'],
        '直播': ['直播', 'LIVE', '实时', '现场', 'NOT', '24'],
        '港澳台': ['港澳', '台湾', 'TVB', 'ATV', '公视', '华视', '台视', '中视', '东森', '中天', '凤凰', '澳亚', 'CHANNEL', 'CH5', 'CH8', '频道', 'VIUTV', 'RTHK', '明珠台', 'HOY', 'ASTRO', '欢喜台', 'AOD', 'AEC', 'QJ'],
        '其他': []
    }
    
    for ch in channels:

        # 过滤掉不需要的 group_title
        if ch.get('group_title') in exclude_groups:
            continue

        name = ch.get('channel_name', '')
        orig_group = ch.get('group_title', '')  # 保存原始分组
        ch['_orig_group'] = orig_group
        
        # 根据频道名称重新分类（不依赖原有分组）
        new_group = '其他'
        for category, keywords in category_map.items():
            if any(keyword.upper() in name.upper() for keyword in keywords):
                new_group = category
                break
        
        # 更新频道分组
        ch['group_title'] = new_group
        reclassified.append(ch)
    
    # 按分组排序
    group_order = list(category_map.keys())
    def get_group_index(ch):
        group = ch.get('group_title', '其他')
        return group_order.index(group) if group in group_order else len(group_order)
    
    reclassified.sort(key=lambda x: (get_group_index(x), x.get('channel_name', '')))
    
    # 统计新分类
    new_groups = Counter(ch.get('group_title', '其他') for ch in reclassified)
    print(f"\n📁 重新分类结果:")
    for group in group_order:
        count = new_groups.get(group, 0)
        if count > 0:
            print(f"   {group:10s}: {count:4d} 个")
    
    # 打印所有"其他"类别的频道名称（用于分析）
    other_channels = [ch for ch in reclassified if ch.get('group_title') == '其他']
    if other_channels:
        print(f"\n📋 '其他'类别全部频道 (共{len(other_channels)}个):")
        
        # 保存到文件方便分析
        other_file = os.path.join(project_root, 'output', 'iptv', 'other_channels.txt')
        os.makedirs(os.path.dirname(other_file), exist_ok=True)
        with open(other_file, 'w', encoding='utf-8') as f:
            for i, ch in enumerate(other_channels, 1):
                name = ch.get('channel_name', 'N/A')
                orig_group = ch.get('_orig_group', 'N/A')
                url = ch.get('url', '')[:50]
                f.write(f"{i:5d}. [{orig_group}] {name}\n")
                if i <= 200:  # 只打印前 200 个到控制台
                    print(f"   {i:5d}. [{orig_group}] {name}")
        
        print(f"\n   ... 还有 {len(other_channels) - 200} 个频道")
        print(f"   完整列表已保存到：{other_file}")
        
        # 分析"其他"类别中的高频词
        print(f"\n📊 '其他'类别词频分析:")
        word_counter = Counter()
        for ch in other_channels:
            name = ch.get('channel_name', '')
            # 提取 2-6 个字符的中文词组
            import re
            words = re.findall(r'[\u4e00-\u9fa5]{2,6}', name)
            word_counter.update(words)
            # 也提取英文单词
            en_words = re.findall(r'[A-Za-z0-9]{2,10}', name)
            word_counter.update(en_words)
        
        print("   高频词 Top 50:")
        for word, count in word_counter.most_common(50):
            if count >= 5:  # 只显示出现 5 次以上的词
                print(f"      {word}: {count}次")
    
    # 打印"咪咕赛事"分组的所有频道
    migu_channels = [ch for ch in reclassified if '咪咕' in ch.get('group_title', '') or '咪咕' in ch.get('channel_name', '')]
    if migu_channels:
        print(f"\n📋 '咪咕赛事'相关频道 (共{len(migu_channels)}个):")
        for i, ch in enumerate(migu_channels[:30], 1):
            group = ch.get('group_title', 'N/A')
            name = ch.get('channel_name', 'N/A')
            print(f"   {i:3d}. [{group}] {name}")
    
    return reclassified


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print(" " * 25 + "IPTV 频道分析脚本")
    print("=" * 80)
    
    # 读取 playlist.m3u 文件
    m3u_file = os.path.join(project_root, 'output', 'iptv', 'playlist.m3u')
    if not os.path.exists(m3u_file):
        logger.error(f"M3U 文件不存在：{m3u_file}")
        sys.exit(1)
    
    # 解析频道
    try:
        with open(m3u_file, 'r', encoding='utf-8') as f:
            content = f.read()
        channels = parse_m3u(content)
    except Exception as e:
        logger.error(f"解析 M3U 文件失败：{e}")
        sys.exit(1)
    
    if not channels:
        logger.error("M3U 文件中没有频道")
        sys.exit(1)
    
    print(f"\n� 读取到 {len(channels)} 个频道，开始分析...\n")
    
    # 进行频道分析
    result = analyze_channels(channels)
    
    # 打印报告
    print_channel_analysis_report(result)
    
    # 重新分类并保存
    print(f"\n{'=' * 80}")
    print("开始重新分类和整理...")
    print(f"{'=' * 80}")
    reclassify_and_save(channels)
    
    # # 保存报告到文件
    # report_file = os.path.join(project_root, 'output', 'iptv', 'analysis_report.txt')
    # try:
    #     os.makedirs(os.path.dirname(report_file), exist_ok=True)
    #     with open(report_file, 'w', encoding='utf-8') as f:
    #         # 简单保存文本报告
    #         f.write("IPTV 频道分析报告\n")
    #         f.write("=" * 80 + "\n\n")
    #         f.write(f"频道总数：{result['channel_count']}\n")
    #         f.write(f"分组数：{len(result['groups'])}\n")
    #         f.write(f"频道类型数：{len(result.get('channel_types', {}))}\n")
    #         f.write("\n")
    #         f.write("主要分组:\n")
    #         for group, count in sorted(result['groups'].items(), key=lambda x: -x[1])[:20]:
    #             f.write(f"  {group}: {count} 个\n")
        
    #     logger.info(f"报告已保存到：{report_file}")
    # except Exception as e:
    #     logger.error(f"保存报告失败：{e}")


if __name__ == "__main__":
    main()



