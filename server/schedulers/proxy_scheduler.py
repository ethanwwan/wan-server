"""
Proxy Scheduler - 代理配置同步器
================================

负责从机场订阅 URL 下载 sing-box / Clash 配置，进行兼容性迁移、节点国家标注、规则增强等处理后保存到本地。

主要职责：
  1. 从 PROXY_URLS 下载 sing-box（多个版本）和 Clash 配置
  2. 将旧版配置迁移到 sing-box 1.14.0+ 推荐格式
  3. 为节点添加国家代码后缀（如 "🇯🇵日本 1-JP"）
  4. 添加自定义路由规则（rule_set、特殊域名等）
  5. 同步 singbox.json 到 docker 子目录，供 sing-box docker 使用

参考：
  - sing-box migration 文档: https://sing-box.sagernet.org/migration/
  - sing-box 1.14.0 文档: https://sing-box.sagernet.org/configuration/
"""
import os
import sys
import json
import time
import yaml
import socket
import ipaddress
import re
import logging
import concurrent.futures
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse

import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_PROXY')


# ============================================================
# 配置加载
# ============================================================

def _load_config() -> dict:
    """加载 config.json 并解析为结构化数据"""
    config_path = os.path.join(project_root, 'server', 'input', 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 加载全局配置
_raw = _load_config()
_proxies = _raw['proxy_domains']
cfg = _raw['proxy']

# 代理订阅 URL 列表（按优先级）
PROXY_URLS: List[str] = [cfg['proxy_url1']]
if cfg.get('proxy_url2'):
    PROXY_URLS.append(cfg['proxy_url2'])
if cfg.get('proxy_url3'):
    PROXY_URLS.append(cfg['proxy_url3'])

# Sing-box 版本列表（最新 + 兼容版）
SINGBOX_VERSIONS: List[Tuple[str, str]] = [
    (cfg['singbox_version'], cfg['singbox_output_filename']),
    (cfg['singbox_old_version'], cfg['singbox_old_output_filename']),
]

# Sing-box 资源 URL
SINGBOX_RULESET = cfg['singbox_proxy_ruleset']
SINGBOX_GEOIP_CN = cfg['singbox_geoip_cn']
SINGBOX_GEOSITE_CN = cfg['singbox_geosite_cn']

# 输出路径
OUTPUT_DIR = os.path.join(project_root, 'server', 'output', cfg['output_dir'])

# 调度配置
SCHEDULE_TIME = cfg['schedule_time']
CLASH_OUTPUT_FILENAME = cfg['clash_output_filename']
FIXED_LISTEN_PORT = cfg.get('fixed_listen_port', 7890)
REQUEST_TIMEOUT = _raw['request_timeout']

# 并发控制
MAX_WORKERS = 10
REQUEST_INTERVAL = 2  # 下载间隔（秒）


# ============================================================
# 特殊域名（需要走代理）
# ============================================================

# 域名后缀（匹配整个域名树）
SPECIAL_DOMAIN_SUFFIXES = [
    "cdn77.org", "91selfie.com", "rmhfrtnd.com", "btc620.com",
    "jads.co", "kwai.net", "killcovid2021.com",
    "skrbtuo.cc", "skrbtuo.top",
]

# 精确域名（不含子域名）
SPECIAL_EXACT_DOMAINS = [
    "fans.91selfie.com", "1729130453.rsc.cdn77.org", "go.rmhfrtnd.com",
    "la.btc620.com", "poweredby.jads.co", "s1.kwai.net",
    "vthumb.killcovid2021.com",
]


# ============================================================
# 工具函数
# ============================================================

def _build_url(base: str, proxy_idx: int = None) -> str:
    """构建代理 URL（可选地通过 proxy_domains 中的代理）"""
    if proxy_idx is not None:
        return _proxies[proxy_idx] + '/' + base
    return base


# ============================================================
# 模块 1: DNS 解析与 IP 定位
# ============================================================

# 国家代码映射（tag emoji / 域名 / 城市名 → ISO 代码）
_FLAG_TO_CODE = {
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

_PREFIX_MAP = {
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

# 中文国家关键词
_ZH_KEYWORDS = {
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


def get_server_ip(server: str, log_warning: bool = True) -> Optional[str]:
    """
    获取 server 的 IP 地址

    策略（多级降级）：
      1. 系统 socket.getaddrinfo（走 docker /etc/resolv.conf 的本地 DNS）
         - 在 docker 内会自动使用容器配置的 nameserver
         - 通常是宿主机的 DNS 转发，可靠且快
      2. UDP 查询 4 个公共 DNS（Google/Cloudflare/阿里/Quad9）并发
         - 仅在系统 DNS 失败时降级
         - docker 网络下 UDP/53 可能被防火墙拦截
      3. 返回 None
    """
    DNS_SERVERS = ['8.8.8.8', '1.1.1.1', '223.5.5.5', '9.9.9.9']

    def _dns_udp_query(dns_server: str) -> Optional[str]:
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_server]
            resolver.timeout = 2
            resolver.lifetime = 2
            answers = resolver.resolve(server, 'A')
            for a in answers:
                if a.rdtype == 1:
                    return a.to_text()
        except Exception:
            return None
        return None

    # 阶段 1: 系统 getaddrinfo（走本地 DNS，docker 内走容器 DNS 配置）
    try:
        socket.setdefaulttimeout(3)
        infos = socket.getaddrinfo(server, None, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass

    # 阶段 2: UDP 并发查询公网 DNS（系统 DNS 失败时降级）
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futs = {executor.submit(_dns_udp_query, dns): dns for dns in DNS_SERVERS}
            for fut in concurrent.futures.as_completed(futs):
                if fut.result():
                    return fut.result()
    except Exception:
        pass

    if log_warning:
        logger.warning(f"DNS 解析失败 {server}: 所有方法均不可用")
    return None


def _infer_country_from_server(server: str, tag: str) -> Optional[str]:
    """
    从 server 域名/节点 tag 推断国家代码（3 级降级）

    优先级：
      1. tag 中已有的国旗 emoji
      2. server 域名前缀
      3. tag 文本中的国家关键词
    """
    # 1. 国旗 emoji
    for flag, code in _FLAG_TO_CODE.items():
        if flag in tag:
            return code

    # 2. server 域名前缀
    server_lower = server.lower()
    first_part = re.split(r'[.\-_]', server_lower)[0]
    if first_part in _PREFIX_MAP:
        return _PREFIX_MAP[first_part]
    for prefix in sorted(_PREFIX_MAP.keys(), key=len, reverse=True):
        if first_part.startswith(prefix):
            return _PREFIX_MAP[prefix]

    # 3. 中文关键词（优先于英文，避免短前缀误判）
    for keyword, code in sorted(_ZH_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in tag:
            return code

    # 4. 英文关键词
    tag_lower = tag.lower()
    for prefix in sorted(_PREFIX_MAP.keys(), key=len, reverse=True):
        if prefix in tag_lower:
            return _PREFIX_MAP[prefix]

    return None


def get_ip_location(ip: str) -> Optional[str]:
    """
    通过 IP 定位获取国家代码（仅当 IP 不是 fakeip 段时有效）

    FakeIP 段：198.18.0.0/15（IANA 保留），所有 IP 定位服务都会拒绝
    """
    try:
        if ipaddress.ip_address(ip) in ipaddress.ip_network('198.18.0.0/15'):
            return None
    except ValueError:
        return None

    # ipinfo.io
    try:
        resp = requests.get(f"https://ipinfo.io/{ip}/country", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        country = resp.text.strip()
        if country:
            return country
    except Exception:
        pass

    # ip-api.com
    try:
        resp = requests.get(f"https://ip-api.com/json/{ip}?fields=countryCode", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success":
            return data["countryCode"]
    except Exception:
        pass

    return None


# ============================================================
# 模块 2: URL 可用性检测（全量探测，短路返回）
# ============================================================

def _tcp_probe(server: str, port: int = 443, timeout: float = 3.0) -> bool:
    """TCP 端口连通性探测（不发送数据，只建立连接）"""
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
        if not infos:
            return False
        ip = infos[0][4][0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        finally:
            sock.close()
    except Exception:
        return False


def _udp_probe(server: str, port: int = 443, timeout: float = 3.0) -> bool:
    """UDP 端口可达性探测（用于 hysteria2 / tuic 等 QUIC 协议节点）

    原理：通过 connect() 将 UDP socket 关联到目标地址，这样内核会把收到的
    ICMP Port Unreachable / Network Unreachable / Host Unreachable 等错误
    以 ConnectionRefusedError / OSError 形式投递给下一次 send/recv。

    判定规则：
      - send 后 recv 收到 UDP 响应 → False（端口有人在响应非预期包，不算 hysteria2）
      - ConnectionRefusedError → False（明确收到 ICMP Port Unreachable，端口未监听）
      - 其他 OSError（network/host unreachable）→ False（IP 层不可达）
      - socket.timeout → True（未收到任何响应，视为网络层可达）
        注：防火墙静默丢包也会走到这里，因此本探测存在"防火墙假阳性"
    """
    sock = None
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(server, port, type=socket.SOCK_DGRAM)
        if not infos:
            return False
        ip = infos[0][4][0]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))  # 关键：connect 后内核关联 ICMP 错误
        sock.send(b'\x00')

        try:
            data = sock.recv(64)
            # 收到任何 UDP 响应都算"端口在监听但协议不对"，判失败
            return False
        except socket.timeout:
            # 超时 = 没收到 ICMP 也没收到 UDP 响应，视为可达
            return True
    except ConnectionRefusedError:
        # 明确收到 ICMP Port Unreachable → 端口未监听 → 不可达
        return False
    except OSError:
        # 其他网络错误（host unreachable / network unreachable） → 不可达
        return False
    except Exception:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _check_url_available(
    config: dict,
    timeout: float = 3.0,
) -> Tuple[bool, int, int]:
    """
    检测 URL 是否可用（协议感知全量探测，任意一个通过即短路返回）

    协议探测策略：
      - hysteria2 / tuic : UDP 探测
      - 其他 TCP 协议    : TCP 探测

    Returns:
        (是否可用, 已发现的可用数, 节点总数)
    """
    outbounds = config.get('outbounds', [])
    UDP_TYPES = {'hysteria2', 'tuic'}

    udp_nodes = []
    tcp_nodes = []
    for ob in outbounds:
        ob_type = ob.get('type')
        server = ob.get('server')
        port = ob.get('server_port', 443)
        if not server:
            continue
        if ob_type in UDP_TYPES:
            udp_nodes.append((server, port))
        elif ob_type in ('vless', 'vmess', 'trojan', 'ss', 'ssr', 'http', 'https', 'socks5'):
            tcp_nodes.append((server, port))

    nodes = udp_nodes + tcp_nodes
    if not nodes:
        return True, 0, 0

    available = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as executor:
        futs = {}
        for srv, port in udp_nodes:
            futs[executor.submit(_udp_probe, srv, port, timeout)] = srv
        for srv, port in tcp_nodes:
            futs[executor.submit(_tcp_probe, srv, port, timeout)] = srv

        for fut in concurrent.futures.as_completed(futs):
            if fut.result():
                available += 1
                # 短路：任意一个通过即可，立即取消剩余探测
                for pending in futs:
                    pending.cancel()
                break

    return available >= 1, available, len(nodes)


# ============================================================
# 模块 3: 节点国家标签（独立、可选）
# ============================================================

def _add_country_tags(
    config: dict,
    ip_cache: Dict[str, Optional[str]] = None,
    country_cache: Dict[str, Optional[str]] = None,
) -> None:
    """
    为节点添加国家代码后缀（如 "🇯🇵日本 1" -> "🇯🇵日本 1-JP"）

    这是独立的逻辑：
      - 只添加标签，不影响节点可用性
      - 失败完全跳过，不报错
      - 使用缓存避免重复查询
    """
    outbounds = config.get('outbounds', [])
    if not outbounds:
        return

    nodes_to_process = [
        (i, ob.get('server'), ob.get('tag'))
        for i, ob in enumerate(outbounds)
        if ob.get('type') in ('hysteria2', 'tuic', 'vless')
        and ob.get('server')
        and ob.get('tag')
    ]
    if not nodes_to_process:
        return

    def _resolve_country(server: str, tag: str):
        """DNS 解析 + IP 地理位置查询（带缓存）"""
        # DNS 解析
        if ip_cache is not None and server in ip_cache:
            ip = ip_cache[server]
        else:
            ip = get_server_ip(server, log_warning=False)
            if ip_cache is not None:
                ip_cache[server] = ip
        if not ip:
            return None, ip, None

        # IP 定位
        if country_cache is not None and ip in country_cache:
            country = country_cache[ip]
        else:
            country = get_ip_location(ip)
            if country_cache is not None:
                country_cache[ip] = country

        # 兜底：从域名/tag 推断
        if not country:
            country = _infer_country_from_server(server, tag)

        if not country:
            return None, ip, None
        return f"{tag}-{country}", ip, country

    tag_map: Dict[str, str] = {}
    dns_resolved = 0
    country_tagged = 0
    max_workers = min(MAX_WORKERS, len(nodes_to_process))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_node = {
            executor.submit(_resolve_country, srv, node_tag): (idx, node_tag)
            for idx, srv, node_tag in nodes_to_process
        }
        for future in concurrent.futures.as_completed(future_to_node):
            idx, old_tag = future_to_node[future]
            try:
                new_tag, ip, _ = future.result()
                if ip:
                    dns_resolved += 1
                if new_tag and new_tag != old_tag:
                    outbounds[idx]['tag'] = new_tag
                    tag_map[old_tag] = new_tag
                    country_tagged += 1
            except Exception:
                pass

    # 更新 selector/urltest 中的节点引用
    for item in outbounds:
        if item.get('type') in ('selector', 'urltest'):
            old_outbounds = item.get('outbounds', [])
            new_outbounds = [tag_map.get(t, t) for t in old_outbounds]
            if new_outbounds != old_outbounds:
                item['outbounds'] = new_outbounds

    total = len(nodes_to_process)
    logger.info(f"节点 DNS 解析: {dns_resolved}/{total} 个可用")
    logger.info(f"节点国家标签: {country_tagged}/{total} 个已添加")


# ============================================================
# 模块 4: sing-box 兼容性迁移（基于官方文档）
# ============================================================
# 参考: https://sing-box.sagernet.org/migration/

def _migrate_legacy_inbounds(config: dict) -> dict:
    """
    迁移旧版 inbound 字段到 sing-box 1.11.0+ rule actions

    迁移的字段（1.13.0 已移除）：
      - inbound.sniff → rule action: sniff
      - inbound.domain_strategy → rule action: resolve
      - inbound.sniff_override_destination → 丢弃（无对应字段）
    """
    inbounds = config.get('inbounds', [])
    if not inbounds:
        return config

    sniff_targets: List[str] = []
    domain_strategies: Dict[str, str] = {}

    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        tag = inbound.get('tag', '')

        if inbound.pop('sniff', None):
            sniff_targets.append(tag)

        # sniff_override_destination 在 1.13.0+ 已移除，直接丢弃
        inbound.pop('sniff_override_destination', None)

        strategy = inbound.pop('domain_strategy', None)
        if strategy:
            domain_strategies[tag] = strategy

    if not sniff_targets and not domain_strategies:
        return config

    route = config.setdefault('route', {})
    rules = route.setdefault('rules', [])

    new_rules: List[dict] = []
    for tag, strategy in domain_strategies.items():
        new_rules.append({
            "inbound": [tag] if tag else [],
            "action": "resolve",
            "strategy": strategy,
        })
    for tag in sniff_targets:
        new_rules.append({
            "inbound": [tag] if tag else [],
            "action": "sniff",
        })

    # 新规则插入到最前面
    route['rules'] = new_rules + rules
    return config


def _migrate_special_outbounds(config: dict) -> dict:
    """
    迁移特殊类型 outbound（dns、block）到 sing-box 1.11.0+ rule actions

      - type=dns  outbound → 移除（用 route.rules action: hijack-dns）
      - type=block outbound → 移除（route.rules 中 outbound: block 改为 action: reject）
    """
    outbounds = config.get('outbounds', [])
    if not outbounds:
        return config

    special_tags: Dict[str, str] = {}  # tag -> 'dns' or 'block'
    new_outbounds: List[dict] = []

    for ob in outbounds:
        if isinstance(ob, dict) and ob.get('type') in ('dns', 'block'):
            tag = ob.get('tag', '')
            if tag:
                special_tags[tag] = ob.get('type')
        else:
            new_outbounds.append(ob)

    if not special_tags:
        return config

    config['outbounds'] = new_outbounds

    # 清理 selector/urltest 中对特殊 outbound 的引用
    for ob in new_outbounds:
        if ob.get('type') in ('selector', 'urltest'):
            ob['outbounds'] = [t for t in ob.get('outbounds', []) if t not in special_tags]

    # 更新 route.rules
    route = config.setdefault('route', {})
    rules = route.setdefault('rules', [])

    for r in rules:
        if not isinstance(r, dict):
            continue
        r_outbound = r.get('outbound')
        referenced_tags = []
        if isinstance(r_outbound, str):
            referenced_tags = [r_outbound]
        elif isinstance(r_outbound, list):
            referenced_tags = r_outbound

        # 如果规则引用了 block outbound
        if any(t in special_tags and special_tags[t] == 'block' for t in referenced_tags):
            r['action'] = 'reject'
            if 'outbound' in r:
                del r['outbound']

    return config


def _migrate_legacy_dns(config: dict) -> dict:
    """
    迁移旧版 DNS servers 格式到 sing-box 1.12.0+ 推荐格式

    支持的转换（按 address scheme）：
      - local            → {type: local}
      - tcp://1.1.1.1    → {type: tcp, server: 1.1.1.1}
      - 1.1.1.1          → {type: udp, server: 1.1.1.1}
      - tls://1.1.1.1    → {type: tls, server: 1.1.1.1}
      - https://1.1.1.1/dns-query → {type: https, server: 1.1.1.1, path: /dns-query}
      - quic://1.1.1.1   → {type: quic, server: 1.1.1.1}
      - h3://1.1.1.1/dns-query   → {type: h3, server: 1.1.1.1, path: /dns-query}
      - dhcp://auto      → {type: dhcp}
      - dhcp://en0       → {type: dhcp, interface: en0}
      - fakeip           → {type: fakeip}
      - rcode://xxx      → 移除（1.12.0+ 用 dns.rules action: predefined）
    """
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    servers = dns.get('servers', [])
    if not isinstance(servers, list):
        return config

    new_servers: List[dict] = []
    for idx, s in enumerate(servers):
        if isinstance(s, str):
            new_servers.append({"tag": f"dns-{idx}", "address": s})
            continue

        if not isinstance(s, dict):
            new_servers.append(s)
            continue

        # 新格式（已有 type）直接保留
        if 'type' in s:
            new_servers.append(s)
            continue

        # 旧格式（只有 address，没有 type）需要转换
        new_s = _convert_dns_server(s, idx)
        if new_s is not None:
            new_servers.append(new_s)

    dns['servers'] = new_servers

    # 清理 dns.rules 中已废弃的 outbound 字段
    for r in dns.get('rules', []):
        if isinstance(r, dict) and 'outbound' in r:
            del r['outbound']

    return config


def _convert_dns_server(s: dict, idx: int) -> Optional[dict]:
    """将单个旧版 DNS server 转换为新版"""
    address = s.get('address', '')
    tag = s.get('tag', f"dns-{idx}")
    detour = s.get('detour')

    if not address:
        return s

    # rcode → 静默移除（1.12.0+ 用 dns.rules action: predefined 替代）
    if address.startswith('rcode://'):
        return None

    # fakeip
    if address == 'fakeip':
        new_s = {'type': 'fakeip', 'tag': tag}
        for k in ['inet4_range', 'inet6_range']:
            if k in s:
                new_s[k] = s[k]
        return new_s

    new_s = {'tag': tag}
    if detour:
        new_s['detour'] = detour

    parsed = urlparse(address)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or parsed.path

    if scheme in ('tcp', 'tls', 'https', 'quic', 'h3'):
        new_s['type'] = scheme
        new_s['server'] = host
        if scheme in ('https', 'h3') and parsed.path and parsed.path != '/':
            new_s['path'] = parsed.path
    elif scheme == 'dhcp':
        new_s['type'] = 'dhcp'
        if host and host != 'auto':
            new_s['interface'] = host
    elif scheme == '':
        # 无 scheme，假设是 UDP
        new_s['type'] = 'udp'
        new_s['server'] = address
    else:
        # 未知 scheme，保留原样
        return s

    # 保留其他字段
    for k in ['client_subnet', 'strategy', 'address_resolver']:
        if k in s:
            new_s[k] = s[k]

    return new_s


# ============================================================
# 模块 5: 自定义规则与配置规范化
# ============================================================

def _normalize_inbound_ports(config: dict) -> dict:
    """
    统一所有 inbound 的 listen_port 为固定值（FIXED_LISTEN_PORT，默认 7890）

    不同机场订阅可能返回不同端口（2080、2333、2334 等），
    固定为同一端口以匹配 docker 容器端口和 clash 默认端口。
    """
    for inbound in config.get('inbounds', []):
        if not isinstance(inbound, dict):
            continue
        if 'listen_port' in inbound:
            inbound['listen_port'] = FIXED_LISTEN_PORT
        if inbound.get('type') in ('mixed', 'socks', 'http'):
            inbound['listen'] = '127.0.0.1'
    return config


def _ensure_proxy_inbound(config: dict, for_docker: bool = False) -> dict:
    """
    确保配置中有 mixed/socks inbound（用于代理接收）

    参数:
        for_docker: 是否为 docker 容器准备配置
                    - True: 移除 tun inbound（容器内无 /dev/net/tun）
                    - False: 保留 tun（普通客户端可用）

    处理逻辑：
      1. 如果 for_docker，移除所有 tun inbound
      2. 移除多余的 socks inbound（避免与 mixed 端口冲突）
      3. 如果没有 mixed，自动添加一个 mixed inbound
    """
    inbounds = config.get('inbounds', [])

    # 1. docker 模式：移除所有 tun inbound（容器内无 /dev/net/tun 设备）
    if for_docker:
        inbounds[:] = [
            ib for ib in inbounds
            if isinstance(ib, dict) and ib.get('type') != 'tun'
        ]

    # 2. 检查是否有 mixed inbound
    has_mixed = any(
        isinstance(ib, dict) and ib.get('type') == 'mixed'
        for ib in inbounds
    )

    # 3. 如果已有 mixed，移除多余的 socks inbound（避免端口冲突）
    if has_mixed:
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]
        return config

    # 4. 如果没有 mixed，但有 socks，移除 socks（避免单独占端口），后面会添加 mixed
    if any(isinstance(ib, dict) and ib.get('type') == 'socks' for ib in inbounds):
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]

    # 5. 自动添加标准 mixed inbound
    inbounds.append({
        'type': 'mixed',
        'tag': 'mixed-in',
        'listen': '127.0.0.1',
        'listen_port': FIXED_LISTEN_PORT,
    })
    return config


def _process_docker_config(config: dict) -> dict:
    """
    Docker 容器专用的 sing-box 配置处理

    与正常客户端配置的差异：
      1. 移除 tun inbound（容器内无 /dev/net/tun 设备）
      2. 移除 socks inbound（避免与 mixed 端口冲突）
      3. 移除 DNS server 的 detour 字段（避免启动时 DNS 死锁）
      4. 优先用国内 DNS 作为 default_domain_resolver（启动时下载 rule_set）

    注意：此函数应在 process_config 之后调用，会基于已处理的配置再调整
    """
    import copy
    # 深拷贝避免修改原配置
    config = copy.deepcopy(config)

    # 1. 移除 tun inbound
    inbounds = config.get('inbounds', [])
    inbounds[:] = [
        ib for ib in inbounds
        if isinstance(ib, dict) and ib.get('type') != 'tun'
    ]

    # 2. 移除 socks inbound（避免与 mixed 端口冲突）
    #    mixed inbound 本身支持 SOCKS 协议，所以保留 mixed 即可
    has_mixed = any(
        isinstance(ib, dict) and ib.get('type') == 'mixed'
        for ib in inbounds
    )
    if has_mixed:
        socks_count = sum(1 for ib in inbounds if isinstance(ib, dict) and ib.get('type') == 'socks')
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]
        if socks_count:
            logger.info(f"Docker 配置: 已移除 {socks_count} 个 socks inbound (避免端口冲突)")

    logger.info(f"Docker 配置: 剩余 {len(inbounds)} 个 inbound ({[ib.get('type') for ib in inbounds]})")

    # 2. 移除 DNS server 的 detour（避免 DNS 死锁）
    dns = config.get('dns')
    if isinstance(dns, dict):
        for srv in dns.get('servers', []):
            if isinstance(srv, dict) and 'detour' in srv:
                del srv['detour']

    # 3. 强制使用国内 DNS 作为 default_domain_resolver
    #    启动时 sing-box 需要解析 gh-proxy.org 等下载 rule_set
    #    用国内 DNS (223.5.5.5) 避免 1.1.1.1:443 被墙
    if isinstance(dns, dict):
        servers = dns.get('servers', [])
        # 找国内 DNS server
        preferred_keywords = ['223.5.5.5', '119.29.29.29', 'ali_dns', 'dns_local',
                              'doh.pub', 'local']
        best_dns_tag = None
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            tag = srv.get('tag', '').lower()
            server = str(srv.get('server', ''))
            for kw in preferred_keywords:
                if kw in tag or kw in server:
                    best_dns_tag = srv.get('tag')
                    break
            if best_dns_tag:
                break

        if best_dns_tag:
            route = config.setdefault('route', {})
            route['default_domain_resolver'] = {'server': best_dns_tag}
            logger.info(f"Docker 配置: default_domain_resolver → {best_dns_tag} (国内 DNS)")

    return config


def _optimize_dns_rules(config: dict) -> dict:
    """
    优化 DNS 规则（国内使用场景）

    国内使用 singbox 客户端时：
      - 默认所有 DNS 查询走 local（国内 DNS）
      - clash_mode=global 时才走 remote

    优化策略：
      1. 默认规则（无匹配条件）走 local
      2. 找到第一个无匹配条件的规则，强制改为 server: local
      3. 确保 clash_mode=global 走 remote（如果是 1.1.1.1，提示风险）
    """
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    servers = dns.get('servers', [])
    rules = dns.get('rules', [])

    # 找 local/remote DNS server
    local_tag = None
    remote_tag = None
    for srv in servers:
        if not isinstance(srv, dict):
            continue
        tag = srv.get('tag', '')
        server = str(srv.get('server', ''))
        if '223.5.5.5' in server or 'ali' in tag.lower() or 'local' in tag.lower():
            local_tag = tag
        elif '1.1.1.1' in server or '8.8.8.8' in server or 'google' in tag.lower() or 'remote' in tag.lower():
            remote_tag = tag

    if not local_tag:
        return config  # 没有 local DNS，跳过

    # 1. 找到第一个无匹配条件的规则（默认规则）→ 改为 local
    has_default_rule = False
    for r in rules:
        if not isinstance(r, dict):
            continue
        # 跳过带匹配条件的规则
        match_keys = {'domain', 'domain_suffix', 'domain_keyword', 'domain_regex',
                       'geosite', 'rule_set', 'clash_mode', 'port', 'network',
                       'inbound', 'query_type', 'ip_version', 'protocol'}
        if any(k in r for k in match_keys):
            continue
        # 这是默认规则（无匹配条件）
        r['server'] = local_tag
        has_default_rule = True
        break

    # 2. 如果没有默认规则，添加一个
    if not has_default_rule:
        # 找到合适的位置（clash_mode 规则之后）
        insert_pos = 0
        for i, r in enumerate(rules):
            if isinstance(r, dict) and r.get('clash_mode'):
                insert_pos = i + 1
                break
        rules.insert(insert_pos, {'server': local_tag})
        has_default_rule = True

    return config


def _ensure_default_domain_resolver(config: dict) -> dict:
    """
    确保 route 中有 default_domain_resolver（sing-box 1.12.0+ 必需）

    用于解析 outbound 中的 server 域名（如 h1bbzqxxa.892622.xyz）和
    rule_set URL 中的域名（如 gh-proxy.org）。

    选择策略：优先选国内可访问的 DNS server（如 223.5.5.5），
    避免启动时 1.1.1.1:443 被墙导致 sing-box 无法启动。
    """
    route = config.setdefault('route', {})
    if route.get('default_domain_resolver'):
        return config

    dns = config.get('dns', {})
    servers = dns.get('servers', [])

    # 优先级：国内 DNS > 国外 DNS
    # 国内常用：223.5.5.5（阿里）、119.29.29.29（DNSPod）、doh.pub
    preferred_keywords = ['223.5.5.5', '119.29.29.29', 'ali_dns', 'dns_local',
                          'doh.pub', 'local']

    def _find_best_dns(servers: list) -> Optional[str]:
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            tag = srv.get('tag', '')
            server = srv.get('server', '')
            # 优先匹配国内 DNS
            for kw in preferred_keywords:
                if kw in tag.lower() or kw in server.lower():
                    return tag or server
        # 兜底：返回第一个有 tag 的
        return next(
            (srv.get('tag') for srv in servers if isinstance(srv, dict) and srv.get('tag')),
            None,
        )

    default_tag = _find_best_dns(servers)

    if not default_tag:
        # 兜底：添加一个内置 DNS server（阿里 DNS）
        if not servers:
            servers.append({
                'type': 'udp',
                'tag': 'default',
                'server': '223.5.5.5',
            })
            dns['servers'] = servers
        default_tag = _find_best_dns(servers) or 'default'

    route['default_domain_resolver'] = {'server': default_tag}
    return config


def add_route_rules(config: dict) -> dict:
    """添加自定义路由规则（rule_set、特殊域名、最终规则）"""
    route = config.get('route', {})

    # 默认最终出口
    route['final'] = "direct"

    # === 找到第一个 selector outbound 作为代理出口 ===
    # 完全使用机场返回的实际 tag，不做任何硬编码/兜底猜测
    # 如果机场返回的 selector 名字是 "节点选择" / "Proxy" / 其他，都直接用
    proxy_outbound_tag = None
    for ob in config.get('outbounds', []):
        if isinstance(ob, dict) and ob.get('type') == 'selector' and ob.get('tag'):
            proxy_outbound_tag = ob.get('tag')
            break

    # 如果完全没有 selector outbound，跳过添加规则
    if not proxy_outbound_tag:
        return config

    # === rule_set 处理 ===
    # 策略：保留机场自己的 rule_set，添加我们需要的（去重）
    route.setdefault('rule_set', [])
    existing_tags = {rs.get("tag") for rs in route['rule_set']}

    new_rule_sets = [
        {"type": "remote", "tag": "geoip-cn", "format": "binary",
         "url": _build_url(SINGBOX_GEOIP_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "geosite-cn", "format": "binary",
         "url": _build_url(SINGBOX_GEOSITE_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "Global", "format": "source",
         "url": _build_url(SINGBOX_RULESET, 0), "download_detour": "direct"},
    ]
    for rs in new_rule_sets:
        if rs["tag"] not in existing_tags:
            route['rule_set'].append(rs)

    # === route.rules 处理 ===
    # 重要：不覆盖机场自带的 sniff / hijack-dns / clash_mode 等规则
    # 只添加特殊域名和 Global rule_set
    route.setdefault('rules', [])

    # 检查是否已有 Global rule_set 规则
    has_global_rule = any(
        isinstance(r, dict) and r.get('rule_set') == 'Global'
        for r in route['rules']
    )

    rules_to_add = []
    if not has_global_rule:
        rules_to_add.append({"rule_set": "Global", "outbound": proxy_outbound_tag})

    # 添加特殊域名规则（避免与现有域名规则重复）
    existing_domain_suffix = set()
    existing_domain = set()
    for r in route['rules']:
        if not isinstance(r, dict):
            continue
        if isinstance(r.get('domain_suffix'), list):
            for d in r['domain_suffix']:
                # 去掉前导点
                clean_d = d.lstrip('.') if isinstance(d, str) and d.startswith('.') else d
                existing_domain_suffix.add(clean_d)
        if isinstance(r.get('domain'), list):
            existing_domain.update(r['domain'])

    # 过滤需要添加的特殊域名
    new_special_suffix = [f".{d}" for d in SPECIAL_DOMAIN_SUFFIXES
                          if d not in existing_domain_suffix]
    new_special_exact = [d for d in SPECIAL_EXACT_DOMAINS
                         if d not in existing_domain]

    if new_special_suffix:
        rules_to_add.append({
            "domain_suffix": new_special_suffix,
            "outbound": proxy_outbound_tag,
        })
    if new_special_exact:
        rules_to_add.append({
            "domain": new_special_exact,
            "outbound": proxy_outbound_tag,
        })

    # 在最前面添加（特殊域名优先），其他追加
    if rules_to_add:
        route['rules'] = rules_to_add + route['rules']

    config['route'] = route
    return config


def process_config(config: dict) -> dict:
    """
    处理 sing-box 配置：迁移 + 标准化 + 添加规则

    执行顺序：
      1. 迁移旧版 inbound 字段
      2. 迁移旧版 DNS servers
      3. 迁移特殊 outbound（dns/block）
      4. 标准化 inbound 端口
      5. 确保有 proxy inbound（mixed/socks）
      6. 添加自定义路由规则
      7. 优化 DNS 规则（默认走 local 国内 DNS）
      8. 确保 default_domain_resolver
      9. 修复 DNS server 的 detour
    """
    config = _migrate_legacy_inbounds(config)
    config = _migrate_legacy_dns(config)
    config = _migrate_special_outbounds(config)
    config = _normalize_inbound_ports(config)
    config = _ensure_proxy_inbound(config)
    config = add_route_rules(config)
    config = _optimize_dns_rules(config)
    config = _ensure_default_domain_resolver(config)
    config = _fix_dns_server_detour(config)
    return config


def _fix_dns_server_detour(config: dict) -> dict:
    """
    修复 DNS server 的 detour 字段

    sing-box 1.12.0+ 规则：
      - type=local 的 DNS server 用 dialer（默认 = 空 direct outbound）
      - detour: "direct" 对 local 类型是冗余的，会报错
      - https/tls/quic/h3 类型的 DNS server 如果走代理，会导致 DNS 死锁：
        解析代理 server 域名也需要 DNS → 循环依赖

    修复策略：
      - type=local：移除 detour 字段（用默认 dialer）
      - https/tls/quic/h3：移除 detour 字段（用默认 dialer 直连）
        注：https://223.5.5.5/dns-query 等是直连访问国内 DNS
    """
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    for srv in dns.get('servers', []):
        if not isinstance(srv, dict):
            continue
        srv_type = srv.get('type', '')
        detour = srv.get('detour')

        # 移除所有 DNS server 的 detour
        # 让 sing-box 用默认 dialer（= 直连）
        # 避免 DNS 死锁和 sing-box 报错
        if 'detour' in srv:
            del srv['detour']
            if srv_type in ('https', 'tls', 'quic', 'h3'):
                # 国内 DNS（223.5.5.5、119.29.29.29 等）直连访问即可
                # 国外 DNS（8.8.8.8、1.1.1.1）由客户端系统路由处理
                pass  # 静默

    return config


def process_config(config: dict) -> dict:
    """
    处理 sing-box 配置：迁移 + 标准化 + 添加规则

    执行顺序：
      1. 迁移旧版 inbound 字段
      2. 迁移旧版 DNS servers
      3. 迁移特殊 outbound（dns/block）
      4. 标准化 inbound 端口
      5. 添加自定义路由规则
      6. 确保 default_domain_resolver
      7. 修复 DNS server 的 detour
    """
    config = _migrate_legacy_inbounds(config)
    config = _migrate_legacy_dns(config)
    config = _migrate_special_outbounds(config)
    config = _normalize_inbound_ports(config)
    config = add_route_rules(config)
    config = _ensure_default_domain_resolver(config)
    config = _fix_dns_server_detour(config)
    return config


# ============================================================
# 模块 6: sing-box 下载与保存
# ============================================================

def _fetch_config(url: str, user_agent: str) -> Optional[dict]:
    """从 URL 下载 sing-box JSON 配置"""
    try:
        session = requests.Session()
        session.verify = False
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"下载失败 {url}: {e}")
        return None


def _save_singbox_config(config: dict, file_name: str) -> str:
    """
    保存 sing-box 配置到本地

    同时拷贝最新版本（1.14.0）到 docker/ 子目录，供 sing-box docker 容器使用。
    兼容版本（1.11.0）的 singbox_old.json 不拷贝（仅供旧版 sing-box 直接使用）。

    docker 配置会经过 `_process_docker_config` 特殊处理：
      - 移除 tun inbound（容器内无 /dev/net/tun）
      - 移除 DNS server 的 detour（避免 DNS 死锁）
      - 强制使用国内 DNS 作为 default_domain_resolver
    """
    file_path = os.path.join(OUTPUT_DIR, file_name)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    logger.info(f"Singbox 已同步到 {file_path}")

    # 仅最新版（1.14.0，对应 singbox_output_filename）拷贝到 docker/
    # docker 配置需要单独处理（容器环境与客户端不同）
    if file_name == cfg['singbox_output_filename']:
        docker_dir = os.path.join(OUTPUT_DIR, 'docker')
        docker_path = os.path.join(docker_dir, 'config.json')
        os.makedirs(docker_dir, exist_ok=True)
        # docker 专用处理
        docker_config = _process_docker_config(config)
        with open(docker_path, 'w', encoding='utf-8') as f:
            json.dump(docker_config, f, ensure_ascii=False, indent=4)
        logger.info(f"已同步 docker 配置到 {docker_path}")

    return file_path


def _download_singbox(
    version: str,
    file_name: str,
    start_idx: int = 0,
    ip_cache: Dict[str, Optional[str]] = None,
    country_cache: Dict[str, Optional[str]] = None,
) -> int:
    """
    下载 Singbox 配置，支持 url1/url2/url3 切换

    Returns: 成功使用的 URL 索引（>=0），失败返回 -1
    """
    user_agent = f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"

    for idx in range(start_idx, len(PROXY_URLS)):
        url = PROXY_URLS[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Singbox v{version} ({url_label})...")

        config = _fetch_config(url, user_agent)
        if config is None:
            logger.warning(f"Singbox {url_label} 下载失败，尝试下一个 URL")
            continue

        # 模块 A: URL 可用性检测（协议感知 + 短路返回）
        available, avail_cnt, total_cnt = _check_url_available(config, timeout=3.0)
        if available:
            logger.info(f"URL 可用性检测: {avail_cnt}/{total_cnt} 节点协议可达（短路）")
        else:
            logger.warning(f"Singbox {url_label} 全部节点协议不可达，尝试下一个 URL")
            continue

        # 模块 B: 添加国家标签（独立、失败不影响主流程）
        _add_country_tags(config, ip_cache=ip_cache, country_cache=country_cache)

        # 处理配置（迁移 + 标准化 + 规则）
        config = process_config(config)
        _save_singbox_config(config, file_name)
        return idx

    logger.error(f"Singbox v{version} 所有 URL 同步失败")
    return -1


# ============================================================
# 模块 7: Clash 下载与处理
# ============================================================

def _fetch_clash_config(url: str, user_agent: str) -> Optional[dict]:
    """从 URL 下载 Clash YAML 配置"""
    try:
        session = requests.Session()
        session.verify = False
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return yaml.safe_load(resp.content)
    except Exception as e:
        logger.error(f"Clash 下载失败 {url}: {e}")
        return None


def _check_clash_url_available(config: dict) -> bool:
    """检查 Clash URL 是否可用（协议感知探测，任意一个通过即短路）

    协议探测策略：
      - hysteria2 / tuic : UDP 探测（QUIC 协议，TCP 探测无效）
      - 其他 TCP 协议    : TCP 探测
    """
    proxies = config.get('proxies', [])
    # 协议分类：type -> [probe_fn]
    UDP_TYPES = {'hysteria2', 'tuic'}
    TCP_TYPES = {'http', 'https', 'socks5', 'ss', 'ssr',
                 'vmess', 'trojan', 'vless'}

    udp_nodes = []  # (server, port)
    tcp_nodes = []  # (server, port)
    for p in proxies:
        ptype = p.get('type')
        server = p.get('server')
        port = p.get('port', 443)
        if not server:
            continue
        if ptype in UDP_TYPES:
            udp_nodes.append((server, port))
        elif ptype in TCP_TYPES:
            tcp_nodes.append((server, port))

    nodes = udp_nodes + tcp_nodes  # 合并用于统计总数
    if not nodes:
        return True

    available = 0
    probed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as executor:
        futs = {}
        for srv, port in udp_nodes:
            futs[executor.submit(_udp_probe, srv, port, 3.0)] = ('udp', srv)
        for srv, port in tcp_nodes:
            futs[executor.submit(_tcp_probe, srv, port, 3.0)] = ('tcp', srv)

        for fut in concurrent.futures.as_completed(futs):
            probed += 1
            if fut.result():
                available += 1
                # 短路：任意一个节点协议层可达即返回，取消剩余探测
                for pending in futs:
                    pending.cancel()
                break

    logger.info(
        f"Clash URL 可用性检测: {available}/{len(nodes)} 节点协议可达 "
        f"(UDP:{len(udp_nodes)} TCP:{len(tcp_nodes)}, 短路)"
    )
    return available >= 1


def _process_clash_groups(
    config: dict,
    ip_cache: Dict[str, Optional[str]] = None,
    country_cache: Dict[str, Optional[str]] = None,
) -> dict:
    """处理 Clash proxy-groups，给节点名称添加国家代码后缀"""
    proxies = config.get('proxies', [])
    proxy_groups = config.get('proxy-groups', [])

    if not proxies:
        return config

    def _resolve_country(server: str, name: str):
        if ip_cache is not None and server in ip_cache:
            ip = ip_cache[server]
        else:
            ip = get_server_ip(server, log_warning=False)
            if ip_cache is not None:
                ip_cache[server] = ip
        if not ip:
            return None, ip, None
        if country_cache is not None and ip in country_cache:
            country = country_cache[ip]
        else:
            country = get_ip_location(ip)
            if country_cache is not None:
                country_cache[ip] = country
        if not country:
            country = _infer_country_from_server(server, name)
        if not country:
            return None, ip, None
        return f"{name}-{country}", ip, country

    nodes = [
        (i, p.get('server'), p.get('name'))
        for i, p in enumerate(proxies)
        if p.get('server') and p.get('name')
        and p.get('type') in ('hysteria2', 'tuic', 'vless', 'ss', 'ssr', 'vmess', 'trojan')
    ]
    if not nodes:
        return config

    name_map: Dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(nodes))) as executor:
        future_to_node = {
            executor.submit(_resolve_country, srv, name): (i, name)
            for i, srv, name in nodes
        }
        for future in concurrent.futures.as_completed(future_to_node):
            i, old_name = future_to_node[future]
            try:
                new_name, _, _ = future.result()
                if new_name and new_name != old_name:
                    proxies[i]['name'] = new_name
                    name_map[old_name] = new_name
            except Exception:
                pass

    # 更新 proxy-groups 中引用的节点名称
    for group in proxy_groups:
        if group.get('type') in ('select', 'url-test', 'fallback', 'load-balance', 'relay'):
            old_proxies = group.get('proxies', [])
            new_proxies = [name_map.get(p, p) for p in old_proxies]
            if new_proxies != old_proxies:
                group['proxies'] = new_proxies

    return config


def _add_clash_rules(config: dict) -> dict:
    """添加 Clash 通用规则集（Loyalsoldier/clash-rules）"""
    rule_provider_common = {
        'type': 'http', 'format': 'yaml', 'interval': 86400,
    }

    rule_providers = config.get('rule-providers', {})
    rule_providers.update({
        'reject': {**rule_provider_common, 'behavior': 'domain',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/reject.txt', 0),
                   'path': './ruleset/reject.yaml'},
        'icloud': {**rule_provider_common, 'behavior': 'domain',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/icloud.txt', 0),
                   'path': './ruleset/icloud.yaml'},
        'apple': {**rule_provider_common, 'behavior': 'domain',
                  'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/apple.txt', 0),
                  'path': './ruleset/apple.yaml'},
        'google': {**rule_provider_common, 'behavior': 'domain',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/google.txt', 0),
                   'path': './ruleset/google.yaml'},
        'proxy': {**rule_provider_common, 'behavior': 'domain',
                  'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/proxy.txt', 0),
                  'path': './ruleset/proxy.yaml'},
        'direct': {**rule_provider_common, 'behavior': 'domain',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/direct.txt', 0),
                   'path': './ruleset/direct.yaml'},
        'private': {**rule_provider_common, 'behavior': 'domain',
                    'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/private.txt', 0),
                    'path': './ruleset/private.yaml'},
        'gfw': {**rule_provider_common, 'behavior': 'domain',
                'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/gfw.txt', 0),
                'path': './ruleset/gfw.yaml'},
        'global': {**rule_provider_common, 'behavior': 'domain',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/blackmatrix7/ios_rule_script@release/rule/Clash/Global/Global_Domain_For_Clash.txt', 0),
                   'path': './ruleset/global.yaml'},
        'tld-not-cn': {**rule_provider_common, 'behavior': 'domain',
                       'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/tld-not-cn.txt', 0),
                       'path': './ruleset/tld-not-cn.yaml'},
        'telegramcidr': {**rule_provider_common, 'behavior': 'ipcidr',
                         'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/telegramcidr.txt', 0),
                         'path': './ruleset/telegramcidr.yaml'},
        'cncidr': {**rule_provider_common, 'behavior': 'ipcidr',
                   'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/cncidr.txt', 0),
                   'path': './ruleset/cncidr.yaml'},
        'lancidr': {**rule_provider_common, 'behavior': 'ipcidr',
                    'url': _build_url('https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/lancidr.txt', 0),
                    'path': './ruleset/lancidr.yaml'},
    })
    config['rule-providers'] = rule_providers

    # 前置规则
    prepend_rules = [
        *[f"DOMAIN,{domain},🚀 节点选择" for domain in SPECIAL_EXACT_DOMAINS],
        "RULE-SET,google,🚀 节点选择",
        "RULE-SET,proxy,🚀 节点选择",
        "RULE-SET,gfw,🚀 节点选择",
        "RULE-SET,global,🚀 节点选择",
        "RULE-SET,telegramcidr,🚀 节点选择,no-resolve",
        "RULE-SET,tld-not-cn,🚀 节点选择",
        "RULE-SET,private,DIRECT",
        "RULE-SET,reject,REJECT",
        "RULE-SET,icloud,DIRECT",
        "RULE-SET,apple,DIRECT",
        "RULE-SET,direct,DIRECT",
        "RULE-SET,lancidr,DIRECT,no-resolve",
        "RULE-SET,cncidr,DIRECT,no-resolve",
        "GEOIP,LAN,DIRECT,no-resolve",
        "GEOIP,CN,DIRECT,no-resolve",
    ]

    # 合并：前置规则 + 原有规则（去重）
    old_rules = config.get('rules', [])
    if old_rules and old_rules[-1].startswith('MATCH,'):
        old_rules = old_rules[:-1]
    combined = list(prepend_rules)
    for r in old_rules:
        if r not in combined:
            combined.append(r)
    combined.append("MATCH,DIRECT")
    config['rules'] = combined

    return config


def _process_clash_config(
    config: dict,
    ip_cache: Dict[str, Optional[str]] = None,
    country_cache: Dict[str, Optional[str]] = None,
) -> dict:
    """处理 Clash 配置：节点标签 + 通用规则"""
    config = _process_clash_groups(config, ip_cache=ip_cache, country_cache=country_cache)
    config = _add_clash_rules(config)
    return config


def _download_clash(
    start_idx: int = 0,
    ip_cache: Dict[str, Optional[str]] = None,
    country_cache: Dict[str, Optional[str]] = None,
) -> bool:
    """下载 Clash 配置，支持 url1/url2/url3 切换"""
    user_agent = "clash-verge/2.0.0"
    file_name = CLASH_OUTPUT_FILENAME

    for idx in range(start_idx, len(PROXY_URLS)):
        url = PROXY_URLS[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Clash ({url_label})...")

        config = _fetch_clash_config(url, user_agent)
        if config is None:
            logger.warning(f"Clash {url_label} 下载失败，尝试下一个 URL")
            continue

        # URL 可用性检测
        if not _check_clash_url_available(config):
            logger.warning(f"Clash {url_label} URL 可用性检测失败，尝试下一个 URL")
            continue

        # 处理配置
        config = _process_clash_config(config, ip_cache=ip_cache, country_cache=country_cache)

        # 保存
        file_path = os.path.join(OUTPUT_DIR, file_name)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f"Clash ({url_label}) 已同步到 {file_path}")
        return True

    logger.error("Clash 所有 URL 同步失败")
    return False


# ============================================================
# 模块 8: 同步入口
# ============================================================

def sync() -> bool:
    """
    同步所有代理配置

    流程：
      1. 下载 sing-box（最新 + 兼容版）
      2. 下载 Clash 配置
      3. 共享 DNS 解析缓存（同一组 server 只解析一次）
    """
    # 共享 DNS 解析缓存：所有版本共用
    ip_cache: Dict[str, Optional[str]] = {}
    country_cache: Dict[str, Optional[str]] = {}

    success_count = 0
    start_idx = 0

    for i, (ver, fname) in enumerate(SINGBOX_VERSIONS):
        if i > 0:
            logger.info(f"等待 {REQUEST_INTERVAL} 秒后继续...")
            time.sleep(REQUEST_INTERVAL)

        result = _download_singbox(ver, fname, start_idx, ip_cache=ip_cache, country_cache=country_cache)
        if result >= 0:
            success_count += 1
            start_idx = result  # 下次从成功使用的 URL 开始
        else:
            start_idx = 0  # 重试 url1

    logger.info(f"等待 {REQUEST_INTERVAL} 秒后下载 Clash 配置...")
    time.sleep(REQUEST_INTERVAL)
    if _download_clash(start_idx, ip_cache=ip_cache, country_cache=country_cache):
        success_count += 1

    if success_count > 0:
        return True
    logger.error("Proxy 全部版本同步失败")
    return False


def run():
    """运行调度器：立即执行一次 + 每天定时执行"""
    sync()
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    run()
