import os
import sys
import json
import time
import yaml
import concurrent.futures
from typing import Optional, Tuple, List, Union
import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_PROXY')

_raw = json.load(open(os.path.join(project_root, 'server', 'input', 'config.json')))
_proxies = _raw['proxy_domains']
cfg = _raw['proxy']
PROXY_URLS: List[str] = [cfg['proxy_url1']]
if cfg.get('proxy_url2'):
    PROXY_URLS.append(cfg['proxy_url2'])
SINGBOX_VERSIONS = [
    (cfg['singbox_version'], cfg['singbox_output_filename']),
    (cfg['singbox_old_version'], cfg['singbox_old_output_filename']),
]
SINGBOX_RULESET = cfg['singbox_proxy_ruleset']
SINGBOX_GEOIP_CN = cfg['singbox_geoip_cn']
SINGBOX_GEOSITE_CN = cfg['singbox_geosite_cn']
OUTPUT_DIR = os.path.join(project_root, 'server', 'output', cfg['output_dir'])
SCHEDULE_TIME = cfg['schedule_time']
CLASH_OUTPUT_FILENAME = cfg['clash_output_filename']

# 特殊域名后缀（需要走代理的特定域名后缀，匹配整个域名树）
SPECIAL_DOMAIN_SUFFIXES = [
    "cdn77.org",
    "91selfie.com",
    "rmhfrtnd.com",
    "btc620.com",
    "jads.co",
    "kwai.net",
    "killcovid2021.com",
    "skrbtuo.cc",
    "skrbtuo.top",
]

# 特殊精确域名（需要走代理的特定完整域名，不含子域名）
SPECIAL_EXACT_DOMAINS = [
    "fans.91selfie.com",
    "1729130453.rsc.cdn77.org",
    "go.rmhfrtnd.com",
    "la.btc620.com",
    "poweredby.jads.co",
    "s1.kwai.net",
    "vthumb.killcovid2021.com",
]


REQUEST_TIMEOUT = _raw['request_timeout']


MAX_WORKERS = 10


def _build_url(base: str, proxy_idx: int = None) -> str:
    if proxy_idx is not None:
        return _proxies[proxy_idx] + '/' + base
    return base


def get_server_ip(server: str) -> Optional[str]:
    try:
        resp = requests.get(f"https://dns.google/resolve",
                            params={"name": server, "type": "A"},
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        answers = data.get("Answer", [])
        for a in answers:
            if a.get("type") == 1:
                return a["data"]
        logger.warning(f"DNS 解析失败 {server}: 无 A 记录")
        return None
    except Exception as e:
        logger.warning(f"DNS 解析异常 {server}: {e}")
        return None


def get_ip_location(ip: str) -> Optional[str]:
    try:
        resp = requests.get(f"https://ipinfo.io/{ip}/country",
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        country = resp.text.strip()
        if country:
            return country
    except Exception:
        pass
    try:
        resp = requests.get(f"https://ip-api.com/json/{ip}?fields=countryCode",
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success":
            return data["countryCode"]
    except Exception:
        pass
    logger.warning(f"IP 定位失败 {ip}: 所有服务均不可用")
    return None


def get_node_country_info(server: str, tag: str) -> Tuple[Optional[str], str, Optional[str]]:
    ip = get_server_ip(server)
    if not ip:
        return None, server, None
    country = get_ip_location(ip)
    if not country:
        return None, ip, None
    new_tag = f"{tag}-{country}"
    return new_tag, ip, country


def process_outbounds(config: dict) -> dict:
    outbounds = config.get('outbounds', [])
    if not outbounds:
        return config

    nodes_to_process = []
    for i, item in enumerate(outbounds):
        item_type = item.get('type')
        server = item.get('server')
        tag = item.get('tag')
        if item_type in ('hysteria2', 'tuic', 'vless') and server and tag:
            nodes_to_process.append((i, server, tag))

    if not nodes_to_process:
        return config

    tag_map = {}
    total = len(nodes_to_process)
    max_workers = min(MAX_WORKERS, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_node = {
            executor.submit(get_node_country_info, server, tag): (i, tag)
            for i, server, tag in nodes_to_process
        }
        for future in concurrent.futures.as_completed(future_to_node):
            i, old_tag = future_to_node[future]
            try:
                new_tag, ip, country = future.result()
                if new_tag:
                    outbounds[i]['tag'] = new_tag
                    tag_map[old_tag] = new_tag
            except Exception as e:
                logger.error(f"处理节点失败: {e}")

    for item in outbounds:
        item_type = item.get('type')
        if item_type in ('selector', 'urltest'):
            old_outbounds = item.get('outbounds', [])
            new_outbounds = []
            for old_tag in old_outbounds:
                new_outbounds.append(tag_map.get(old_tag, old_tag))
            if new_outbounds != old_outbounds:
                item['outbounds'] = new_outbounds

    return config


def add_route_rules(config: dict) -> dict:
    route = config.get('route', {})
    route['final'] = "direct"
    route.setdefault('rule_set', [])
    route['rule_set'] = [rs for rs in route['rule_set']
                         if rs.get("tag") not in ("geoip-cn", "geosite-cn")]
    route['rule_set'].extend([
        {"type": "remote", "tag": "geoip-cn", "format": "binary",
         "url": _build_url(SINGBOX_GEOIP_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "geosite-cn", "format": "binary",
         "url": _build_url(SINGBOX_GEOSITE_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "Global", "format": "source",
         "url": _build_url(SINGBOX_RULESET, 0), "download_detour": "direct"},
    ])
    route.setdefault('rules', [])
    route['rules'].extend([
        {
            "domain_suffix": [f".{d}" for d in SPECIAL_DOMAIN_SUFFIXES],
            "outbound": "🚀 节点选择"
        },
        {
            "domain": SPECIAL_EXACT_DOMAINS,
            "outbound": "🚀 节点选择"
        },
        {"rule_set": "Global", "outbound": "🚀 节点选择"},
    ])
    config['route'] = route
    return config


def process_config(config: dict) -> dict:
    config = add_route_rules(config)
    config = process_outbounds(config)
    return config


def get_config_json(is_latest: bool = True) -> dict:
    file_name = cfg['singbox_output_filename'] if is_latest else cfg['singbox_old_output_filename']
    path = os.path.join(OUTPUT_DIR, file_name)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
    return {}


def _check_all_servers_available(config: dict) -> bool:
    """
    检查配置中所有节点的 server DNS 是否可解析
    返回 True 表示至少有一个 server 可用，False 表示全部不可用
    """
    outbounds = config.get('outbounds', [])
    nodes_to_check = []
    for item in outbounds:
        item_type = item.get('type')
        server = item.get('server')
        if item_type in ('hysteria2', 'tuic', 'vless') and server:
            nodes_to_check.append(server)

    if not nodes_to_check:
        # 没有需要检测的节点，认为是有效的
        return True

    total = len(nodes_to_check)
    available_count = 0
    max_workers = min(MAX_WORKERS, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_server_ip, server): server for server in nodes_to_check}
        for future in concurrent.futures.as_completed(futures):
            try:
                ip = future.result()
                if ip:
                    available_count += 1
            except Exception as e:
                logger.warning(f"DNS 检测异常: {e}")

    logger.info(f"DNS 检测: {available_count}/{total} 个节点可用")
    return available_count > 0


def _fetch_config(url: str, user_agent: str) -> Optional[dict]:
    """从指定 URL 下载配置"""
    try:
        session = requests.Session()
        session.verify = False
        headers = {"User-Agent": user_agent}
        resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"下载失败 {url}: {e}")
        return None


def _download_singbox(version: str, file_name: str, start_idx: int = 0) -> bool:
    """下载 Singbox 配置，支持 url1 和 url2 切换"""
    user_agent = f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"

    for idx in range(start_idx, len(PROXY_URLS)):
        url = PROXY_URLS[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Singbox v{version} ({url_label})...")

        config = _fetch_config(url, user_agent)
        if config is None:
            logger.warning(f"Singbox {url_label} 下载失败，尝试下一个 URL")
            continue

        # 检测所有节点的 DNS 是否可用
        logger.info(f"检测 Singbox {url_label} 中所有节点的 DNS...")
        if not _check_all_servers_available(config):
            logger.warning(f"Singbox {url_label} 所有节点 DNS 检测失败，尝试下一个 URL")
            continue

        # 处理配置
        config = process_config(config)

        file_path = os.path.join(OUTPUT_DIR, file_name)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"Singbox v{version} ({url_label}) 已同步到 {file_path}")
        return idx

    logger.error(f"Singbox v{version} 所有 URL 同步失败")
    return -1


def _fetch_clash_config(url: str, user_agent: str) -> Optional[dict]:
    """从指定 URL 下载 Clash 配置（YAML 格式）"""
    try:
        session = requests.Session()
        session.verify = False
        headers = {"User-Agent": user_agent}
        resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Clash 配置是 YAML 格式
        # 注意：YAML 1.1 中 yes/no 会被解析为 bool，这里使用 safe_load
        return yaml.safe_load(resp.content)
    except Exception as e:
        logger.error(f"Clash 下载失败 {url}: {e}")
        return None


def _check_clash_servers_available(config: dict) -> bool:
    """
    检查 Clash 配置中所有 proxy 的 server DNS 是否可解析
    返回 True 表示至少有一个 server 可用，False 表示全部不可用
    """
    proxies = config.get('proxies', [])
    nodes_to_check = []
    for p in proxies:
        server = p.get('server')
        proxy_type = p.get('type')
        # 仅检查需要域名解析的代理类型
        if server and proxy_type in ('http', 'https', 'socks5', 'ss', 'ssr', 'vmess', 'trojan', 'vless', 'hysteria2', 'tuic'):
            nodes_to_check.append(server)

    if not nodes_to_check:
        return True

    total = len(nodes_to_check)
    available_count = 0
    max_workers = min(MAX_WORKERS, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_server_ip, server): server for server in nodes_to_check}
        for future in concurrent.futures.as_completed(futures):
            try:
                ip = future.result()
                if ip:
                    available_count += 1
            except Exception as e:
                logger.warning(f"DNS 检测异常: {e}")

    logger.info(f"Clash DNS 检测: {available_count}/{total} 个节点可用")
    return available_count > 0


def _process_clash_groups(config: dict) -> dict:
    """
    处理 Clash 配置的 proxies，给节点名称添加国家代码后缀
    同时更新 proxy-groups 中引用的名称
    """
    proxies = config.get('proxies', [])
    proxy_groups = config.get('proxy-groups', [])

    if not proxies:
        return config

    # 收集需要处理的节点
    nodes_to_process = []
    for i, p in enumerate(proxies):
        server = p.get('server')
        name = p.get('name')
        proxy_type = p.get('type')
        if server and name and proxy_type in ('hysteria2', 'tuic', 'vless', 'ss', 'ssr', 'vmess', 'trojan'):
            nodes_to_process.append((i, server, name))

    if not nodes_to_process:
        return config

    tag_map = {}
    total = len(nodes_to_process)
    max_workers = min(MAX_WORKERS, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_node = {
            executor.submit(get_node_country_info, server, name): (i, name)
            for i, server, name in nodes_to_process
        }
        for future in concurrent.futures.as_completed(future_to_node):
            i, old_name = future_to_node[future]
            try:
                new_name, ip, country = future.result()
                if new_name and new_name != old_name:
                    proxies[i]['name'] = new_name
                    tag_map[old_name] = new_name
            except Exception as e:
                logger.error(f"处理节点失败: {e}")

    # 更新 proxy-groups 中引用的节点名称
    for group in proxy_groups:
        if group.get('type') in ('select', 'url-test', 'fallback', 'load-balance', 'relay'):
            old_proxies = group.get('proxies', [])
            new_proxies = [tag_map.get(p, p) for p in old_proxies]
            if new_proxies != old_proxies:
                group['proxies'] = new_proxies

    return config


def _add_clash_rules(config: dict) -> dict:
    """
    添加 Clash 通用规则集配置（rule-providers 和 rules）
    参考 Loyalsoldier/clash-rules 标准规则集
    """
    # 规则集通用配置
    rule_provider_common = {
        'type': 'http',
        'format': 'yaml',
        'interval': 86400
    }

    # 规则集配置（使用 Loyalsoldier/clash-rules）
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

    # 通用前置规则（域名 → 代理，不包含 MATCH）
    prepend_rules = [
        # === 特定精确域名（走代理）===
        *[f"DOMAIN,{domain},🚀 节点选择" for domain in SPECIAL_EXACT_DOMAINS],

        # === 规则集 ===
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

    # 在原规则前添加前置规则，并去重
    old_rules = config.get('rules', [])
    # 移除原 MATCH 规则（最后会被 MATCH,DIRECT 覆盖）
    if old_rules and old_rules[-1].startswith('MATCH,'):
        old_rules = old_rules[:-1]
    # 合并：前置规则 + 原有规则（去重）
    combined = list(prepend_rules)
    for r in old_rules:
        if r not in combined:
            combined.append(r)
    # MATCH 兜底规则必须放在最后
    combined.append("MATCH,DIRECT")
    config['rules'] = combined

    return config


def _process_clash_config(config: dict) -> dict:
    """处理 Clash 配置：节点标签 + 通用规则"""
    config = _process_clash_groups(config)
    config = _add_clash_rules(config)
    return config


def _download_clash() -> bool:
    """下载 Clash 配置，支持 url1 和 url2 切换"""
    # 使用标准的 Clash User-Agent，包含 "clash" 关键字以获取机场响应头
    user_agent = "clash-verge/2.0.0"
    file_name = CLASH_OUTPUT_FILENAME

    for idx in range(len(PROXY_URLS)):
        url = PROXY_URLS[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Clash ({url_label})...")

        config = _fetch_clash_config(url, user_agent)
        if config is None:
            logger.warning(f"Clash {url_label} 下载失败，尝试下一个 URL")
            continue

        # 检测所有 proxy 的 server DNS 是否可用
        logger.info(f"检测 Clash {url_label} 中所有 proxy 的 DNS...")
        if not _check_clash_servers_available(config):
            logger.warning(f"Clash {url_label} 所有 proxy DNS 检测失败，尝试下一个 URL")
            continue

        # 处理配置（添加国家标签 + 通用规则）
        config = _process_clash_config(config)

        # 保存为 YAML 格式
        file_path = os.path.join(OUTPUT_DIR, file_name)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f"Clash ({url_label}) 已同步到 {file_path}")
        return True

    logger.error("Clash 所有 URL 同步失败")
    return False


def sync() -> bool:
    # 记录第一次成功使用的 URL 索引，后续下载直接从该索引开始
    start_idx = 0
    success_count = 0
    REQUEST_INTERVAL = 2  # 每次下载之间的间隔（秒）

    for i, (ver, fname) in enumerate(SINGBOX_VERSIONS):
        # 第一次下载不需要等待，后续下载前需要等待避免请求过快
        if i > 0:
            logger.info(f"等待 {REQUEST_INTERVAL} 秒后继续...")
            time.sleep(REQUEST_INTERVAL)

        result = _download_singbox(ver, fname, start_idx)
        if result >= 0:
            success_count += 1
            start_idx = result  # 下次从成功使用的 URL 开始
        else:
            # 下载失败，重置为从 url1 开始（给 url1 一次重试机会）
            start_idx = 0

    # Clash 下载前也等待一下
    logger.info(f"等待 {REQUEST_INTERVAL} 秒后下载 Clash 配置...")
    time.sleep(REQUEST_INTERVAL)
    clash_result = _download_clash()
    if clash_result:
        success_count += 1

    if success_count > 0:
        return True
    logger.error("Proxy 全部版本同步失败")
    return False


def run():
    sync()
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    # run()
    _download_clash()