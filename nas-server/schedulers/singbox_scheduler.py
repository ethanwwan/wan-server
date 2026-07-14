import os
import sys
import json
import time
import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_SINGBOX')

_config = json.load(open(os.path.join(project_root, 'nas-server', 'input', 'config.json')))
_proxies = _config['proxy_domains']
cfg = _config['singbox']
SINGBOX_URL = cfg['source_url']
VERSIONS = [
    (cfg['version'], cfg['output_file']),
    (cfg['old_version'], cfg['old_output_file']),
]
PROXY_RULESET = cfg['proxy_ruleset']
GEOIP_CN = cfg['geoip_cn']
GEOSITE_CN = cfg['geosite_cn']
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output', cfg['output_dir'])
SCHEDULE_TIME = cfg['schedule_time']
REQUEST_TIMEOUT = _config['request_timeout']


def _build_url(base: str, proxy_idx: int = None) -> str:
    if proxy_idx is not None:
        return _proxies[proxy_idx] + '/' + base
    return base


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
            "outbound": "\U0001f680 \u8282\u70b9\u9009\u62e9"
        },
        {"rule_set": "Global", "outbound": "\U0001f680 \u8282\u70b9\u9009\u62e9"},
    ])
    config['route'] = route
    return config


def _download(version: str, file_name: str) -> bool:
    if cfg['use_proxy']:
        attempts = list(range(len(_proxies)))
    else:
        attempts = [None]

    for idx in attempts:
        url = _build_url(SINGBOX_URL, idx) if idx is not None else SINGBOX_URL
        label = f"v{version}" + (f" (代理 {idx + 1}/{len(attempts)})" if cfg['use_proxy'] and idx > 0 else "")
        try:
            logger.info(f"正在下载 Singbox 配置 {label}...")
            session = requests.Session()
            session.verify = False
            headers = {"User-Agent": f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"}
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            config = resp.json()
            config = add_route_rules(config)

            file_path = os.path.join(OUTPUT_DIR, file_name)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.info(f"Singbox v{version} 已同步到 {file_path}")
            return True
        except Exception as e:
            is_last = idx == attempts[-1]
            logger.warning(f"同步失败 {label}: {e}{', 切换代理...' if not is_last else ''}")
            if is_last:
                logger.error(f"Singbox v{version} 配置同步失败 (已用完全部代理)")
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
