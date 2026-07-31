"""
常量与配置加载

统一管理脚本所需的常量，避免在多处重复硬编码。
"""
import os
import json
from typing import List, Tuple


# 项目根目录
def get_project_root() -> str:
    """获取项目根目录（包含 server/ 目录的目录）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 配置加载
# ============================================================

def load_config() -> dict:
    """加载 server/input/config.json"""
    config_path = os.path.join(
        get_project_root(), 'server', 'input', 'config.json'
    )
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 通用常量
# ============================================================

# HTTP 下载相关
REQUEST_TIMEOUT = 15             # 单次 HTTP 请求超时（秒）
REQUEST_INTERVAL = 2             # 多次下载之间的间隔（秒）
MAX_WORKERS = 10                 # 线程池最大并发数

# 探测相关
PROBE_TIMEOUT = 3.0              # TCP/UDP 探测超时（秒）
PROBE_CONCURRENCY = 16           # 探测并发数上限

# DNS 解析降级目标
FALLBACK_DNS_SERVERS = ['8.8.8.8', '1.1.1.1', '223.5.5.5', '9.9.9.9']


# ============================================================
# 调度相关
# ============================================================

def build_proxy_urls(cfg_proxy: dict) -> List[str]:
    """构建代理订阅 URL 列表（按优先级）"""
    urls = [cfg_proxy['proxy_url1']]
    if cfg_proxy.get('proxy_url2'):
        urls.append(cfg_proxy['proxy_url2'])
    if cfg_proxy.get('proxy_url3'):
        urls.append(cfg_proxy['proxy_url3'])
    return urls


def build_singbox_versions(cfg_proxy: dict) -> List[Tuple[str, str]]:
    """构建 singbox 版本列表 [(version, output_filename), ...]"""
    return [
        (cfg_proxy['singbox_version'], cfg_proxy['singbox_output_filename']),
        (cfg_proxy['singbox_old_version'], cfg_proxy['singbox_old_output_filename']),
    ]


# ============================================================
# Clash 规则相关常量
# ============================================================

SPECIAL_DOMAIN_SUFFIXES = [
    "cdn77.org", "91selfie.com", "rmhfrtnd.com", "btc620.com",
    "jads.co", "kwai.net", "killcovid2021.com",
    "skrbtuo.cc", "skrbtuo.top",
]

SPECIAL_EXACT_DOMAINS = [
    "fans.91selfie.com", "1729130453.rsc.cdn77.org", "go.rmhfrtnd.com",
    "la.btc620.com", "poweredby.jads.co", "s1.kwai.net",
    "vthumb.killcovid2021.com",
]

# Loyalsoldier/clash-rules 的 jsdelivr CDN URL（key → (cname, behavior)）
LOYALSOLDIER_RULES: dict = {
    'reject':       ('reject.txt', 'domain'),
    'icloud':       ('icloud.txt', 'domain'),
    'apple':        ('apple.txt', 'domain'),
    'google':       ('google.txt', 'domain'),
    'proxy':        ('proxy.txt', 'domain'),
    'direct':       ('direct.txt', 'domain'),
    'private':      ('private.txt', 'domain'),
    'gfw':          ('gfw.txt', 'domain'),
    'tld-not-cn':   ('tld-not-cn.txt', 'domain'),
    'telegramcidr': ('telegramcidr.txt', 'ipcidr'),
    'cncidr':       ('cncidr.txt', 'ipcidr'),
    'lancidr':      ('lancidr.txt', 'ipcidr'),
}

LOYALSOLDIER_BASE = 'https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/'
BLACKMATRIX7_GLOBAL = (
    'https://cdn.jsdelivr.net/gh/blackmatrix7/ios_rule_script@release/'
    'rule/Clash/Global/Global_Domain_For_Clash.txt'
)


# ============================================================
# 国家代码映射（节点命名推断）
# ============================================================

FLAG_TO_CODE = {
    '🇭🇰': 'HK', '🇯🇵': 'JP', '🇸🇬': 'SG', '🇺🇸': 'US',
    '🇬🇧': 'GB', '🇩🇪': 'DE', '🇫🇷': 'FR', '🇷🇺': 'RU',
    '🇳🇱': 'NL', '🇰🇷': 'KR', '🇹🇼': 'TW', '🇨🇳': 'CN',
    '🇨🇦': 'CA', '🇦🇺': 'AU', '🇮🇳': 'IN', '🇹🇭': 'TH',
    '🇻🇳': 'VN', '🇮🇩': 'ID', '🇲🇾': 'MY', '🇵🇭': 'PH',
    '🇧🇷': 'BR', '🇲🇽': 'MX', '🇮🇹': 'IT', '🇪🇸': 'ES',
    '🇨🇭': 'CH', '🇸🇪': 'SE', '🇳🇴': 'NO', '🇫🇮': 'FI',
    '🇩🇰': 'DK', '🇵🇱': 'PL', '🇹🇷': 'TR', '🇺🇦': 'UA',
    '🇦🇪': 'AE', '🇸🇦': 'SA', '🇮🇱': 'IL', '🇪🇬': 'EG',
    '🇿🇦': 'ZA', '🇦🇷': 'AR', '🇨🇱': 'CL', '🇨🇴': 'CO',
}

PREFIX_MAP = {
    'jp': 'JP', 'jpn': 'JP', 'tokyo': 'JP', 'osaka': 'JP',
    'hk': 'HK', 'hkg': 'HK', 'hongkong': 'HK', 'hong': 'HK',
    'sg': 'SG', 'sin': 'SG', 'singapore': 'SG',
    'us': 'US', 'usa': 'US', 'america': 'US',
    'uk': 'GB', 'gb': 'GB', 'london': 'GB', 'england': 'GB',
    'de': 'DE', 'ger': 'DE', 'germany': 'DE', 'frankfurt': 'DE',
    'fr': 'FR', 'fra': 'FR', 'france': 'FR', 'paris': 'FR',
    'ru': 'RU', 'rus': 'RU', 'russia': 'RU', 'moscow': 'RU',
    'nl': 'NL', 'nld': 'NL', 'netherlands': 'NL', 'amsterdam': 'NL',
    'kr': 'KR', 'kor': 'KR', 'korea': 'KR', 'seoul': 'KR',
    'tw': 'TW', 'twn': 'TW', 'taiwan': 'TW', 'taipei': 'TW',
    'cn': 'CN', 'chn': 'CN', 'china': 'CN',
    'ca': 'CA', 'can': 'CA', 'canada': 'CA',
    'au': 'AU', 'aus': 'AU', 'australia': 'AU', 'sydney': 'AU',
    'in': 'IN', 'ind': 'IN', 'india': 'IN',
    'th': 'TH', 'tha': 'TH', 'thailand': 'TH', 'bangkok': 'TH',
    'vn': 'VN', 'vnm': 'VN', 'vietnam': 'VN',
    'id': 'ID', 'idn': 'ID', 'indonesia': 'ID',
    'my': 'MY', 'mys': 'MY', 'malaysia': 'MY',
    'ph': 'PH', 'phl': 'PH', 'philippines': 'PH',
    'br': 'BR', 'bra': 'BR', 'brazil': 'BR',
    'mx': 'MX', 'mex': 'MX', 'mexico': 'MX',
    'it': 'IT', 'ita': 'IT', 'italy': 'IT',
    'es': 'ES', 'esp': 'ES', 'spain': 'ES',
    'ch': 'CH', 'che': 'CH', 'switzerland': 'CH', 'zurich': 'CH',
    'se': 'SE', 'swe': 'SE', 'sweden': 'SE', 'stockholm': 'SE',
    'no': 'NO', 'nor': 'NO', 'norway': 'NO',
    'fi': 'FI', 'fin': 'FI', 'finland': 'FI',
    'dk': 'DK', 'dnk': 'DK', 'denmark': 'DK',
    'pl': 'PL', 'pol': 'PL', 'poland': 'PL',
    'tr': 'TR', 'tur': 'TR', 'turkey': 'TR', 'istanbul': 'TR',
    'ua': 'UA', 'ukr': 'UA', 'ukraine': 'UA',
    'ae': 'AE', 'are': 'AE', 'uae': 'AE', 'dubai': 'AE',
    'sa': 'SA', 'sau': 'SA', 'saudi': 'SA',
    'il': 'IL', 'isr': 'IL', 'israel': 'IL',
    'eg': 'EG', 'egy': 'EG', 'egypt': 'EG',
}

ZH_KEYWORDS = {
    '美国': 'US', '日本': 'JP', '香港': 'HK', '香江': 'HK',
    '台湾': 'TW', '新加坡': 'SG', '狮城': 'SG', '韩国': 'KR',
    '英国': 'GB', '伦敦': 'GB', '德国': 'DE', '法兰克福': 'DE',
    '法国': 'FR', '巴黎': 'FR', '俄罗斯': 'RU', '莫斯科': 'RU',
    '荷兰': 'NL', '阿姆斯特丹': 'NL', '澳洲': 'AU', '澳大利亚': 'AU',
    '加拿大': 'CA', '印度': 'IN', '泰国': 'TH', '曼谷': 'TH',
    '越南': 'VN', '印尼': 'ID', '马来西亚': 'MY', '菲律宾': 'PH',
    '巴西': 'BR', '墨西哥': 'MX', '意大利': 'IT', '罗马': 'IT',
    '西班牙': 'ES', '瑞士': 'CH', '瑞典': 'SE', '斯德哥尔摩': 'SE',
    '挪威': 'NO', '芬兰': 'FI', '丹麦': 'DK', '波兰': 'PL',
    '土耳其': 'TR', '伊斯坦布尔': 'TR', '乌克兰': 'UA', '迪拜': 'AE',
    '阿联酋': 'AE', '沙特': 'SA', '以色列': 'IL', '埃及': 'EG',
    '南非': 'ZA', '阿根廷': 'AR', '智利': 'CL', '哥伦比亚': 'CO',
    '西美': 'US', '东美': 'US', '北美': 'US', '南美': 'US',
    '西雅图': 'US', '洛杉矶': 'US', '纽约': 'US', '硅谷': 'US',
    '达拉斯': 'US', '芝加哥': 'US', '迈阿密': 'US', '丹佛': 'US',
    '东京': 'JP', '大阪': 'JP', '名古屋': 'JP', '福冈': 'JP',
    '首尔': 'KR', '釜山': 'KR',
}


# ============================================================
# 协议分类
# ============================================================

# 节点协议探测分类
UDP_PROXY_TYPES = {'hysteria2', 'tuic'}                       # QUIC 协议 → UDP 探测
TCP_PROXY_TYPES = {
    'vless', 'vmess', 'trojan', 'ss', 'ssr',
    'http', 'https', 'socks5',
}                                                              # TCP 协议 → TCP 探测


# ============================================================
# URL 构建工具
# ============================================================

def build_proxied_url(base: str, proxies: List[str], idx: int = 0) -> str:
    """构建通过代理转发的 URL（用 proxies[idx] 做前缀）"""
    if 0 <= idx < len(proxies):
        return proxies[idx] + '/' + base
    return base