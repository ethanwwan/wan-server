"""
Clash 配置处理器

包含：
  - 节点国家标签注入（DNS → IP 定位 → 域名推断）
  - 通用规则注入（Loyalsoldier/clash-rules）
  - 综合处理入口
"""
import concurrent.futures
from typing import Dict, List, Optional

from .constants import (
    MAX_WORKERS, SPECIAL_EXACT_DOMAINS,
    LOYALSOLDIER_RULES, LOYALSOLDIER_BASE, BLACKMATRIX7_GLOBAL,
)
from .dns_resolver import resolve
from .geo_locator import get_ip_country, infer_from_server


# ============================================================
# 节点标签注入
# ============================================================

def _resolve_country(
    server: str,
    name: str,
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
        country = infer_from_server(server, name)

    if not country:
        return None, ip
    return f"{name}-{country}", ip


def process_proxy_groups(
    config: dict,
    ip_cache: Optional[Dict[str, Optional[str]]] = None,
    country_cache: Optional[Dict[str, Optional[str]]] = None,
) -> dict:
    """为 Clash proxy-groups 中的节点添加国家代码后缀"""
    ip_cache = ip_cache if ip_cache is not None else {}
    country_cache = country_cache if country_cache is not None else {}

    proxies = config.get('proxies', [])
    proxy_groups = config.get('proxy-groups', [])
    if not proxies:
        return config

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
            executor.submit(_resolve_country, srv, name, ip_cache, country_cache): (i, name)
            for i, srv, name in nodes
        }
        for future in concurrent.futures.as_completed(future_to_node):
            i, old_name = future_to_node[future]
            try:
                new_name, _ = future.result()
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


# ============================================================
# 通用规则注入
# ============================================================

def _build_rule_providers(proxies: List[str]) -> dict:
    """构建 Loyalsoldier rule-providers 配置"""
    rule_provider_common = {
        'type': 'http', 'format': 'yaml', 'interval': 86400,
    }
    providers = {}
    for key, (filename, behavior) in LOYALSOLDIER_RULES.items():
        # global 用 blackmatrix7 的源
        if key == 'global':
            url = BLACKMATRIX7_GLOBAL
        else:
            url = LOYALSOLDIER_BASE + filename
        providers[key] = {
            **rule_provider_common,
            'behavior': behavior,
            'url': url,
            'path': f'./ruleset/{key}.yaml',
        }
    return providers


def _build_prepend_rules(proxy_group_name: Optional[str]) -> List[str]:
    """构建前置规则列表（动态使用代理组名）"""
    if not proxy_group_name:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.warning("Clash 配置中未找到任何 proxy-group，跳过代理规则注入")
        return [
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

    g = proxy_group_name
    return [
        *[f"DOMAIN,{domain},{g}" for domain in SPECIAL_EXACT_DOMAINS],
        f"RULE-SET,google,{g}",
        f"RULE-SET,proxy,{g}",
        f"RULE-SET,gfw,{g}",
        f"RULE-SET,global,{g}",
        f"RULE-SET,telegramcidr,{g},no-resolve",
        f"RULE-SET,tld-not-cn,{g}",
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


def add_rules(config: dict, proxies: Optional[List[str]] = None) -> dict:
    """
    添加 Clash 通用规则集（Loyalsoldier/clash-rules）

    - 动态获取代理组名（不硬编码，避免引用不存在的 group）
    - 去重：保留原有 rules（去掉尾部 MATCH）
    - 追加我们的规则 + 最终 MATCH,DIRECT
    """
    proxy_groups = config.get('proxy-groups', [])
    proxy_group_name = proxy_groups[0].get('name') if proxy_groups else None

    # rule-providers 注入
    rule_providers = config.get('rule-providers', {})
    rule_providers.update(_build_rule_providers(proxies or []))
    config['rule-providers'] = rule_providers

    # rules 注入
    prepend_rules = _build_prepend_rules(proxy_group_name)
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


# ============================================================
# 综合处理入口
# ============================================================

def process(
    config: dict,
    proxies: Optional[List[str]] = None,
    ip_cache: Optional[Dict[str, Optional[str]]] = None,
    country_cache: Optional[Dict[str, Optional[str]]] = None,
) -> dict:
    """处理 Clash 配置：节点标签 + 通用规则"""
    config = process_proxy_groups(config, ip_cache=ip_cache, country_cache=country_cache)
    config = add_rules(config, proxies=proxies)
    return config