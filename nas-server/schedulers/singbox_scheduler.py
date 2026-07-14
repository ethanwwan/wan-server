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
SINGBOX_VERSION = cfg['version']
GLOBAL_RULESET_URL = cfg['global_ruleset_url']
GEOIP_CN_URL = cfg['geoip_cn_url']
GEOSITE_CN_URL = cfg['geosite_cn_url']
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output', cfg['output_dir'])
OUTPUT_FILE = os.path.join(OUTPUT_DIR, cfg['output_file'])
SCHEDULE_TIME = cfg['schedule_time']
REQUEST_TIMEOUT = cfg['request_timeout']


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
         "url": GEOIP_CN_URL, "download_detour": "direct"},
        {"type": "remote", "tag": "geosite-cn", "format": "binary",
         "url": GEOSITE_CN_URL, "download_detour": "direct"},
        {"type": "remote", "tag": "Global", "format": "source",
         "url": _build_url(GLOBAL_RULESET_URL, 0), "download_detour": "direct"},
    ])
    route.setdefault('rules', [])
    route['rules'].insert(0, {
        "rule_set": "Global",
        "outbound": "\U0001f680 \u8282\u70b9\u9009\u62e9"
    })
    config['route'] = route
    return config


def sync() -> bool:
    if cfg['use_proxy']:
        attempts = list(range(len(_proxies)))
    else:
        attempts = [None]

    for idx in attempts:
        url = _build_url(SINGBOX_URL, idx) if idx is not None else SINGBOX_URL
        label = f" (代理 {idx + 1}/{len(attempts)})" if cfg['use_proxy'] and idx > 0 else ""
        try:
            logger.info(f"正在下载 Singbox 配置{label}...")
            session = requests.Session()
            session.verify = False
            headers = {"User-Agent": f"SFA/1.1{SINGBOX_VERSION} (595; sing-box {SINGBOX_VERSION}; language zh_CN)"}
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            config = resp.json()

            config = add_route_rules(config)

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.info(f"Singbox 配置已同步到 {OUTPUT_FILE}")
            return True
        except Exception as e:
            is_last = idx == attempts[-1]
            logger.warning(f"同步失败{label}: {e}{', 切换代理...' if not is_last else ''}")
            if is_last:
                logger.error(f"Singbox 配置同步失败 (已用完全部代理)")
                return False


def run():
    sync()
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
