import os
import sys
import json
import time
import concurrent.futures
from typing import Optional, Tuple
import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_SINGBOX')

_raw = json.load(open(os.path.join(project_root, 'server', 'input', 'config.json')))
_proxies = _raw['proxy_domains']
cfg = _raw['singbox']
SINGBOX_URL = cfg['source_url']
VERSIONS = [
    (cfg['version'], cfg['output_file']),
    (cfg['old_version'], cfg['old_output_file']),
]
PROXY_RULESET = cfg['proxy_ruleset']
GEOIP_CN = cfg['geoip_cn']
GEOSITE_CN = cfg['geosite_cn']
OUTPUT_DIR = os.path.join(project_root, 'server', 'output', cfg['output_dir'])
SCHEDULE_TIME = cfg['schedule_time']
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
         "url": _build_url(GEOIP_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "geosite-cn", "format": "binary",
         "url": _build_url(GEOSITE_CN, 0), "download_detour": "direct"},
        {"type": "remote", "tag": "Global", "format": "source",
         "url": _build_url(PROXY_RULESET, 0), "download_detour": "direct"},
    ])
    route.setdefault('rules', [])
    route['rules'].extend([
        {
            "domain_suffix": [
                ".cdn77.org", ".91selfie.com", ".rmhfrtnd.com",
                ".btc620.com", ".jads.co", ".kwai.net", ".killcovid2021.com"
            ],
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
    file_name = cfg['output_file'] if is_latest else cfg['old_output_file']
    path = os.path.join(OUTPUT_DIR, file_name)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
    return {}


def _download(version: str, file_name: str) -> bool:
    try:
        logger.info(f"正在下载 Singbox v{version}...")
        session = requests.Session()
        session.verify = False
        headers = {"User-Agent": f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"}
        resp = session.get(SINGBOX_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        config = resp.json()
        config = process_config(config)

        file_path = os.path.join(OUTPUT_DIR, file_name)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"Singbox v{version} 已同步到 {file_path}")
        return True
    except Exception as e:
        logger.error(f"Singbox v{version} 配置同步失败: {e}")
        return False


def sync() -> bool:
    results = [_download(ver, fname) for ver, fname in VERSIONS]
    if any(results):
        return True
    logger.error("Singbox 全部版本同步失败")
    return False


def run():
    sync()
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
