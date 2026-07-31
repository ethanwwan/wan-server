"""
sing-box 配置处理器

包含：
  - 节点国家标签注入（DNS → IP 定位 → 域名推断）
  - 旧版配置迁移（inbounds / DNS servers / special outbounds）
  - 路由规则添加
  - DNS 规则优化
  - 综合处理入口
"""
import re
import copy
import concurrent.futures
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .constants import (
    MAX_WORKERS,
    SPECIAL_DOMAIN_SUFFIXES, SPECIAL_EXACT_DOMAINS,
)
from .dns_resolver import resolve
from .geo_locator import get_ip_country, infer_from_server


# ============================================================
# 节点标签注入
# ============================================================

def _resolve_country(
    server: str,
    tag: str,
    ip_cache: dict,
    country_cache: dict,
) -> Optional[tuple]:
    """DNS 解析 + IP 地理位置查询 + 域名推断（带缓存）"""
    if server in ip_cache:
        ip = ip_cache[server]
    else:
        ip = resolve(server, log_warning=False)
        ip_cache[server] = ip
    if not ip:
        return None

    if ip in country_cache:
        country = country_cache[ip]
    else:
        country = get_ip_country(ip)
        country_cache[ip] = country

    if not country:
        country = infer_from_server(server, tag)

    if not country:
        return None, ip
    return f"{tag}-{country}", ip


def add_country_tags(
    config: dict,
    ip_cache: Optional[Dict[str, Optional[str]]] = None,
    country_cache: Optional[Dict[str, Optional[str]]] = None,
) -> None:
    """
    为节点添加国家代码后缀（如 "🇯🇵日本 1" → "🇯🇵日本 1-JP"）

    失败完全跳过，不影响主流程
    """
    ip_cache = ip_cache if ip_cache is not None else {}
    country_cache = country_cache if country_cache is not None else {}

    outbounds = config.get('outbounds', [])
    if not outbounds:
        return

    nodes = [
        (i, ob.get('server'), ob.get('tag'))
        for i, ob in enumerate(outbounds)
        if ob.get('type') in ('hysteria2', 'tuic', 'vless')
        and ob.get('server') and ob.get('tag')
    ]
    if not nodes:
        return

    tag_map: Dict[str, str] = {}
    dns_resolved = 0
    country_tagged = 0
    max_workers = min(MAX_WORKERS, len(nodes))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_node = {
            executor.submit(_resolve_country, srv, tag, ip_cache, country_cache): (idx, tag)
            for idx, srv, tag in nodes
        }
        for future in concurrent.futures.as_completed(future_to_node):
            idx, old_tag = future_to_node[future]
            try:
                new_tag, ip = future.result()
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
            old_ob = item.get('outbounds', [])
            new_ob = [tag_map.get(t, t) for t in old_ob]
            if new_ob != old_ob:
                item['outbounds'] = new_ob

    from logger import get_logger
    logger = get_logger('NAS_PROXY')
    total = len(nodes)
    logger.info(f"节点 DNS 解析: {dns_resolved}/{total} 个可用")
    logger.info(f"节点国家标签: {country_tagged}/{total} 个已添加")


# ============================================================
# 迁移函数
# ============================================================

def migrate_legacy_inbounds(config: dict) -> dict:
    """迁移旧版 inbound 字段到 sing-box 1.11.0+ rule actions"""
    inbounds = config.get('inbounds', [])
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        # sniff → sniff_override (1.11.0+)
        if 'sniff' in inbound and 'sniff_override' not in inbound:
            inbound['sniff_override'] = inbound.pop('sniff')
        # domain_strategy → sniff_strategy (1.11.0+)
        if 'domain_strategy' in inbound and 'sniff_strategy' not in inbound:
            inbound['sniff_strategy'] = inbound.pop('domain_strategy')
    return config


def migrate_special_outbounds(config: dict) -> dict:
    """迁移 dns/block outbounds 到新格式（sing-box 1.11.0+）"""
    outbounds = config.get('outbounds', [])
    new_outbounds = []
    for ob in outbounds:
        if not isinstance(ob, dict):
            new_outbounds.append(ob)
            continue
        ob_type = ob.get('type', '')
        if ob_type == 'dns':
            # 旧版 dns 类型已废弃，转为 selector + tag
            ob['type'] = 'selector'
            ob.setdefault('tag', 'dns-out')
            ob.setdefault('outbounds', [])
        new_outbounds.append(ob)
    config['outbounds'] = new_outbounds
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


def migrate_legacy_dns(config: dict) -> dict:
    """迁移旧版 DNS servers 格式"""
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config
    servers = dns.get('servers', [])
    new_servers = []
    for i, s in enumerate(servers):
        if not isinstance(s, dict):
            new_servers.append(s)
            continue
        if 'type' in s:
            # 已经是新版格式
            new_servers.append(s)
            continue
        # 旧格式（只有 address，没有 type）需要转换
        new_s = _convert_dns_server(s, i)
        if new_s is not None:
            new_servers.append(new_s)

    dns['servers'] = new_servers

    # 清理 dns.rules 中已废弃的 outbound 字段
    for r in dns.get('rules', []):
        if isinstance(r, dict) and 'outbound' in r:
            del r['outbound']

    return config


# ============================================================
# 端口与 inbound 规范化
# ============================================================

def normalize_inbound_ports(config: dict, fixed_port: int = 7890) -> dict:
    """统一 inbound listen_port 为固定值，避免不同机场端口不一致"""
    for inbound in config.get('inbounds', []):
        if not isinstance(inbound, dict):
            continue
        if 'listen_port' in inbound:
            inbound['listen_port'] = fixed_port
        if inbound.get('type') in ('mixed', 'socks', 'http'):
            inbound['listen'] = '127.0.0.1'
    return config


def ensure_proxy_inbound(config: dict, for_docker: bool = False) -> dict:
    """
    确保配置中有 mixed/socks inbound

    for_docker=True 时移除 tun inbound
    """
    inbounds = config.get('inbounds', [])

    # docker 模式：移除 tun inbound
    if for_docker:
        inbounds[:] = [
            ib for ib in inbounds
            if isinstance(ib, dict) and ib.get('type') != 'tun'
        ]

    has_mixed = any(
        isinstance(ib, dict) and ib.get('type') == 'mixed'
        for ib in inbounds
    )

    # 已有 mixed 时移除多余 socks（避免端口冲突）
    if has_mixed:
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]
        return config

    # 没有 mixed 但有 socks → 移除 socks
    has_socks = any(
        isinstance(ib, dict) and ib.get('type') == 'socks'
        for ib in inbounds
    )
    if has_socks:
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]

    # 没有 mixed 也没有 socks → 添加默认 mixed inbound
    inbounds.append({
        'type': 'mixed',
        'tag': 'mixed-in',
        'listen': '127.0.0.1',
        'listen_port': 7890,
    })
    return config


# ============================================================
# 路由规则
# ============================================================

def add_route_rules(config: dict, ruleset_url: str, geoip_cn_url: str, geosite_cn_url: str,
                    proxies: Optional[List[str]] = None) -> dict:
    """添加自定义路由规则（rule_set + 特殊域名）"""
    proxies = proxies or []
    route = config.get('route', {})

    route['final'] = "direct"

    # 找到第一个 selector outbound 作为代理出口
    proxy_outbound_tag = None
    for ob in config.get('outbounds', []):
        if isinstance(ob, dict) and ob.get('type') == 'selector' and ob.get('tag'):
            proxy_outbound_tag = ob.get('tag')
            break

    if not proxy_outbound_tag:
        return config

    # rule_set
    route.setdefault('rule_set', [])
    existing_tags = {rs.get("tag") for rs in route['rule_set']}

    new_rule_sets = [
        {"type": "remote", "tag": "geoip-cn", "format": "binary",
         "url": geoip_cn_url, "download_detour": "direct"},
        {"type": "remote", "tag": "geosite-cn", "format": "binary",
         "url": geosite_cn_url, "download_detour": "direct"},
        {"type": "remote", "tag": "Global", "format": "source",
         "url": ruleset_url, "download_detour": "direct"},
    ]
    for rs in new_rule_sets:
        if rs["tag"] not in existing_tags:
            route['rule_set'].append(rs)

    # route.rules
    route.setdefault('rules', [])
    has_global_rule = any(
        isinstance(r, dict) and r.get('rule_set') == 'Global'
        for r in route['rules']
    )

    rules_to_add = []
    if not has_global_rule:
        rules_to_add.append({"rule_set": "Global", "outbound": proxy_outbound_tag})

    # 收集现有域名避免重复
    existing_domain_suffix = set()
    existing_domain = set()
    for r in route['rules']:
        if not isinstance(r, dict):
            continue
        if isinstance(r.get('domain_suffix'), list):
            for d in r['domain_suffix']:
                clean_d = d.lstrip('.') if isinstance(d, str) and d.startswith('.') else d
                existing_domain_suffix.add(clean_d)
        if isinstance(r.get('domain'), list):
            existing_domain.update(r['domain'])

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

    if rules_to_add:
        route['rules'] = rules_to_add + route['rules']

    config['route'] = route
    return config


# ============================================================
# DNS 规则优化
# ============================================================

def optimize_dns_rules(config: dict) -> dict:
    """
    优化 DNS 规则（国内使用场景）

    - 默认 DNS 走 local（国内 DNS）
    - clash_mode=global 时走 remote
    """
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    servers = dns.get('servers', [])
    rules = dns.get('rules', [])

    local_tag = None
    remote_tag = None
    for srv in servers:
        if not isinstance(srv, dict):
            continue
        tag = srv.get('tag')
        srv_type = srv.get('type', '')
        if srv_type == 'local' or tag in ('dns-local', 'local'):
            local_tag = tag
        elif srv_type in ('https', 'tls', 'quic', 'udp', 'tcp'):
            remote_tag = tag

    # 把 dns.rules 中的 action: route 改为 server 形式
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get('action')
        if action == 'route':
            server = rule.get('server')
            if server == 'local' and local_tag:
                rule['server'] = local_tag
            elif server == 'remote' and remote_tag:
                rule['server'] = remote_tag

    return config


def ensure_default_domain_resolver(config: dict) -> dict:
    """确保 route.default_domain_resolver 存在"""
    route = config.get('route', {})
    if 'default_domain_resolver' in route:
        return config

    # 找一个合适的 DNS server tag（优先 local）
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    default_tag = None
    for srv in dns.get('servers', []):
        if not isinstance(srv, dict):
            continue
        srv_type = srv.get('type', '')
        if srv_type == 'local':
            default_tag = srv.get('tag')
            break
    if not default_tag:
        for srv in dns.get('servers', []):
            if isinstance(srv, dict) and srv.get('tag'):
                default_tag = srv.get('tag')
                break

    if default_tag:
        route['default_domain_resolver'] = {'server': default_tag}
        config['route'] = route
    return config


def fix_dns_server_detour(config: dict) -> dict:
    """
    修复 DNS server 的 detour 字段

    - type=local：移除 detour（用默认 dialer）
    - https/tls/quic/h3：移除 detour（避免 DNS 死锁）
    """
    dns = config.get('dns')
    if not isinstance(dns, dict):
        return config

    for srv in dns.get('servers', []):
        if not isinstance(srv, dict):
            continue
        if 'detour' in srv:
            del srv['detour']

    return config


# ============================================================
# 综合处理入口
# ============================================================

def process(config: dict, ruleset_url: str, geoip_cn_url: str, geosite_cn_url: str,
            fixed_port: int = 7890) -> dict:
    """
    处理 sing-box 配置（迁移 + 标准化 + 添加规则 + DNS 优化）

    执行顺序：
      1. 迁移旧版 inbound 字段
      2. 迁移特殊 outbound（dns/block）
      3. 迁移旧版 DNS servers
      4. 标准化 inbound 端口
      5. 确保有 proxy inbound
      6. 添加自定义路由规则
      7. 优化 DNS 规则
      8. 确保 default_domain_resolver
      9. 修复 DNS server 的 detour
    """
    config = migrate_legacy_inbounds(config)
    config = migrate_special_outbounds(config)
    config = migrate_legacy_dns(config)
    config = normalize_inbound_ports(config, fixed_port=fixed_port)
    config = ensure_proxy_inbound(config)
    config = add_route_rules(config, ruleset_url, geoip_cn_url, geosite_cn_url)
    config = optimize_dns_rules(config)
    config = ensure_default_domain_resolver(config)
    config = fix_dns_server_detour(config)
    return config