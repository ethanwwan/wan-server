import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

import requests

logger = logging.getLogger("IPTV_UTILS")


@dataclass(frozen=True)
class IPTVConfig:
    DEFAULT_WORKERS: int = 30
    MAX_WORKERS: int = 100
    BATCH_SIZE: int = 300
    HTTP_TIMEOUT: int = 8
    FFMPEG_TIMEOUT: int = 15
    MIN_FPS: int = 20
    MIN_BITRATE: int = 1000
    MIN_RESOLUTION_WIDTH: int = 1920
    MIN_RESOLUTION_HEIGHT: int = 1080
    GROUP_MAPPING: Dict[str, List[str]] = None
    CHANNEL_MAPPING: Dict[str, List[str]] = None

    @classmethod
    def build(cls) -> 'IPTVConfig':
        return cls(
            GROUP_MAPPING={
                '央视频道': ['央视'],
                '卫视频道': ['卫视'],
                '地方频道': ['地方', '浙江频道', '江苏频道', '广东频道', '湖南频道', '湖北频道', '四川频道', '河南频道', '河北频道', '山东频道', '山西频道', '陕西频道', '安徽频道', '福建频道', '江西频道', '辽宁频道', '吉林频道', '黑龙江频道', '北京频道', '上海频道', '天津频道', '重庆频道', '云南频道', '贵州频道', '广西频道', '海南频道', '甘肃频道', '青海频道', '内蒙古频道', '宁夏频道', '新疆频道', '西藏频道'],
                '电影电视': ['电影', '埋堆堆', '电视剧', '剧场', '影视'],
                '体育赛事': ['体育', '咪咕赛事'],
                '少儿教育': ['少儿', '动漫', '儿童', '动画'],
                '综艺娱乐': ['综艺', '音乐'],
                '纪录纪实': ['纪录', '直播中国', '纪实'],
                '国际全球': ['国际', '全球', '外语'],
                '港澳台': ['港·澳·台', '港澳', '港台'],
                '咪视界': ['咪视界', '咪视通'],
                'NewTV': ['NewTV'],
                'iHOT': ['IHOT'],
                'iPanda': ['ipanda']
            },
            CHANNEL_MAPPING={
                '央视频道': ['CCTV', 'CGTN'],
                '卫视频道': ['湖南卫视', '江苏卫视', '浙江卫视', '东方卫视', '北京卫视', '广东卫视', '安徽卫视', '山东卫视', '河南卫视', '河北卫视', '湖北卫视', '四川卫视', '重庆卫视', '天津卫视', '江西卫视', '云南卫视', '贵州卫视', '广西卫视', '苏州4K'],
                '地方频道': ['重庆', '天津', '山东', '山西', '陕西', '福建', '安徽', '贵州', '云南', '广西', '海南', '黑龙江', '吉林', '辽宁', '内蒙古', '宁夏', '新疆', '青海', '甘肃', '西藏', '地方', '广州', '佛山', '江门', '汕头', '深圳', '珠海', '东莞', '中山', '惠州', '肇庆', '清远', '韶关', '河源', '梅州', '汕尾', '揭阳', '阳江', '茂名', '湛江', '潮州', '云浮', '南宁', '南京', '宁波', '杭州', '余杭', '上虞', '湖州', '松阳', '庆元', '民视', '余姚', '开化', '南国', '邢台', '绍兴', '嵊州', '新昌', '福州', '萧山', '钱江', '财经', '新闻综合'],
                '电影电视': ['电影'],
                '体育赛事': ['体育', '足球'],
                '少儿教育': ['少儿', '动画', '卡通', '动漫'],
                '综艺娱乐': ['综艺', '娱乐', '音乐'],
                '国际全球': ['国际', 'UK', '美亚'],
                '纪录纪实': ['纪录', '人文', '历史', '地理', '自然', '生物', '纪实', '睛彩'],
                '港澳台': ['台湾', 'Taiwan', 'TVB', 'ATV', '公视', '华视', '台视', '中视', '东森', '中天', '凤凰', '澳亚', 'CHANNEL', 'CH5', 'CH8', '频道', 'VIUTV', 'RTHK', '明珠台', 'HOY', 'ASTRO', '欢喜台', 'AOD', 'AEC', 'QJ', '港·澳·台', '港澳', '港台'],
                '咪视界': ['咪视界', '咪视通'],
                'NewTV': ['NewTV'],
                'iHOT': ['IHOT'],
                'iPanda': ['ipanda']
            }
        )


IPTV_CONFIG = IPTVConfig.build()


def get_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_cache_path() -> str:
    return os.path.join(get_project_root(), 'output', 'cache', 'fail_cache.json')


def get_output_dir() -> str:
    return os.path.join(get_project_root(), 'output')


def get_input_file_path(filename: str) -> str:
    return os.path.join(get_project_root(), 'input', filename)


class CacheManager:
    _instance: Optional['CacheManager'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cache: Dict[str, str] = {}
        self._load_cache()
        self._initialized = True

    def _load_cache(self):
        try:
            cache_path = get_cache_path()
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            logger.info(f"[缓存] 加载 {len(self._cache)} 条失败记录")
        except Exception as e:
            logger.error(f"[缓存] 加载失败: {e}")
            self._cache = {}

    def save_to_disk(self):
        try:
            cache_path = get_cache_path()
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            logger.info(f"[缓存] 保存 {len(self._cache)} 条记录")
        except Exception as e:
            logger.error(f"[缓存] 保存失败: {e}")

    def get_cache(self) -> Dict[str, str]:
        return self._cache

    def is_in_cache(self, url: str) -> bool:
        return url in self._cache

    def batch_update(self, successes: tuple, failures: tuple):
        removed = sum(1 for url in successes if url in self._cache and self._cache.pop(url, None) is not None)
        added = 0
        for url, fail_type in failures:
            if url not in self._cache:
                self._cache[url] = fail_type
                added += 1
        if removed:
            logger.info(f"[缓存] 移除 {removed} 条成功记录")
        if added:
            logger.info(f"[缓存] 添加 {added} 条失败记录")

    def clear_all(self):
        self._cache = {}
        logger.info("[缓存] 已清空")


def get_cache_manager() -> CacheManager:
    return CacheManager()


def fetch_url(url: str, timeout: int = 20) -> str:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, timeout=timeout, verify=False, headers=headers)
        resp.raise_for_status()
        content = resp.text.strip()
        if not content:
            logger.warning(f"空内容: {url}")
            return ""
        return content
    except requests.exceptions.Timeout:
        logger.error(f"超时: {url}")
        return ""
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP错误: {url}, {e.response.status_code if e.response else 'N/A'}")
        return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {url}, {e}")
        return ""
    except Exception as e:
        logger.error(f"未知错误: {url}, {e}")
        return ""


def parse_m3u(content: str) -> List[Dict]:
    if not content:
        return []
    channels = []
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            url = lines[i + 1].strip()
            if not url or url.startswith('#'):
                continue
            tvg_id = re.search(r'tvg-id="([^"]*)"', line)
            tvg_name = re.search(r'tvg-name="([^"]*)"', line)
            tvg_logo = re.search(r'tvg-logo="([^"]*)"', line)
            group = re.search(r'group-title="([^"]*)"', line)
            comma = re.search(r',(.+)$', line)
            channel_name = ""
            if tvg_name:
                channel_name = tvg_name.group(1).strip()
            elif comma:
                raw_name = comma.group(1).strip()
                channel_name = raw_name.split(',')[-1].strip() if '=' in raw_name else raw_name
            if channel_name and url:
                channels.append({
                    'channel_name': channel_name,
                    'url': url,
                    'tvg_id': tvg_id.group(1).strip() if tvg_id else "",
                    'tvg_name': tvg_name.group(1).strip() if tvg_name else "",
                    'tvg_logo': tvg_logo.group(1).strip() if tvg_logo else "",
                    'group_title': group.group(1).strip() if group else ""
                })
    return channels


def parse_txt(content: str) -> List[Dict]:
    if not content:
        return []
    channels = []
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',')
        if len(parts) >= 2:
            name, url = parts[0].strip(), parts[1].strip()
            if url.startswith(('http://', 'https://')) and name and url:
                channels.append({
                    'channel_name': name, 'url': url,
                    'tvg_id': "", 'tvg_name': "", 'tvg_logo': "", 'group_title': ""
                })
    return channels


def parse_url(url: str, content: str) -> List[Dict]:
    return parse_txt(content) if url.endswith('.txt') else parse_m3u(content)


def build_m3u(channels: List[Dict]) -> str:
    if not channels:
        return ""
    lines = ['#EXTM3U x-tvg-url="https://gh-proxy.org/https://raw.githubusercontent.com/fanmingming/live/refs/heads/main/e.xml"']
    seen = set()
    for ch in channels:
        url = ch.get('url', '')
        if url in seen:
            continue
        seen.add(url)
        parts = []
        for k in ('tvg_id', 'tvg_name', 'tvg_logo', 'group_title'):
            v = ch.get(k, '')
            if v:
                parts.append(f'{k.replace("_", "-")}="{v}"')
        lines.append(f'#EXTINF:-1 {" ".join(parts)},{ch.get("channel_name", "")}')
        lines.append(url)
    return '\n'.join(lines)


def filter_channels(channels: List[Dict]) -> List[Dict]:
    seen_urls = set()
    filtered = []
    skipped = 0
    cache_manager = get_cache_manager()
    for ch in channels:
        url = ch.get('url', '')
        if not url.startswith(('http://', 'https://')):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if cache_manager.is_in_cache(url):
            skipped += 1
            continue
        filtered.append(ch)
    logger.info(f"[缓存] 过滤: {len(channels)}→{len(filtered)}, 跳过缓存 {skipped}")
    return filtered


def classify_channels(channels: List[Dict], keep_unmatched: bool = False) -> List[Dict]:
    result = []
    for ch in channels:
        name = ch.get('channel_name', '').upper()
        group_title = ch.get('group_title', '').upper()
        new_group = '其他'
        for group, keywords in IPTV_CONFIG.GROUP_MAPPING.items():
            if any(kw.upper() in group_title for kw in keywords):
                new_group = group
                break
        if new_group == '其他':
            for group, keywords in IPTV_CONFIG.CHANNEL_MAPPING.items():
                if any(kw.upper() in name for kw in keywords):
                    new_group = group
                    break
        ch['group_title'] = new_group
        if new_group != '其他' or keep_unmatched:
            result.append(ch)
    return result


def fetch_channels(urls: List[str], max_workers: int = 10, limit: int = None) -> List[Dict]:
    all_channels = []
    seen_urls = set()
    logger.info(f"从 {len(urls)} 个 URL 获取频道...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(fetch_url, url): url for url in urls}
        for future in as_completed(futs):
            if limit and len(all_channels) >= limit:
                for f in set(futs) - {future}:
                    f.cancel()
                break
            url = futs[future]
            try:
                content = future.result()
                if content:
                    for ch in parse_url(url, content):
                        ch_url = ch.get('url', '')
                        if ch_url not in seen_urls:
                            seen_urls.add(ch_url)
                            all_channels.append(ch)
                            if limit and len(all_channels) >= limit:
                                break
            except Exception as e:
                logger.error(f"解析失败 {url}: {e}")
    logger.info(f"合并完成: {len(all_channels)} 个频道")
    all_channels = filter_channels(all_channels)
    all_channels = classify_channels(all_channels)
    logger.info(f"分类后: {len(all_channels)} 个频道")
    return all_channels


def save_file(filename: str, content: str, output_dir: str = None) -> bool:
    if not content:
        return False
    if output_dir is None:
        output_dir = get_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"{filename} 已保存")
        return True
    except Exception as e:
        logger.error(f"保存失败: {filename}, {e}")
        return False


def get_file_content(filename: str, input_dir: str = None) -> str:
    if input_dir is None:
        input_dir = get_output_dir()
    path = os.path.join(input_dir, filename)
    if not os.path.exists(path):
        logger.warning(f"文件不存在: {path}")
        return ""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"读取失败: {filename}, {e}")
        return ""


def sort_channels(channels: List[Dict]) -> List[Dict]:
    group_order = ['央视频道', '卫视频道', '地方频道', '电影电视', '体育赛事',
                   '少儿教育', '综艺娱乐', '纪录纪实', '国际全球', '港澳台',
                   '咪视界', 'NewTV', 'iHOT', 'iPanda', '其他']
    def sort_key(ch):
        group = ch.get('group_title', '其他')
        try:
            return (group_order.index(group), ch.get('channel_name', ''))
        except ValueError:
            return (len(group_order), ch.get('channel_name', ''))
    return sorted(channels, key=sort_key)
