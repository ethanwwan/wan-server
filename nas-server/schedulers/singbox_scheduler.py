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

SINGBOX_URL = "https://47.76.155.27/iv/verify_mode.htm?token=9a49f8e2abcce3a0d3fd12e072065cdd"
SINGBOX_VERSION = "1.12.14"
GLOBAL_RULESET_URL = "https://gh-proxy.org/https://raw.githubusercontent.com/ethanwwan/sing-box-rules/refs/heads/main/rule_json/Global_All.json"
GEOIP_CN_URL = "https://gh-proxy.com/https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"
GEOSITE_CN_URL = "https://gh-proxy.com/https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-cn.srs"

OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output', 'singbox')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'config.json')
DOCKER_DIR = os.path.join(OUTPUT_DIR, 'docker')
DOCKER_FILE = os.path.join(DOCKER_DIR, 'config.json')
MAX_RETRIES = 2
REQUEST_TIMEOUT = 20


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
         "url": GLOBAL_RULESET_URL, "download_detour": "direct"},
    ])
    route.setdefault('rules', [])
    route['rules'].insert(0, {
        "rule_set": "Global",
        "outbound": "\U0001f680 \u8282\u70b9\u9009\u62e9"
    })
    config['route'] = route
    return config


def generate_docker_config(config: dict):
    docker_config = config.copy()
    docker_config['inbounds'] = [
        inbound for inbound in docker_config.get('inbounds', [])
        if inbound.get('type') != 'tun'
    ]
    os.makedirs(DOCKER_DIR, exist_ok=True)
    with open(DOCKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(docker_config, f, ensure_ascii=False, indent=4)
    logger.info(f"Docker 配置已生成到 {DOCKER_FILE}")


def sync() -> bool:
    for attempt in range(1 + MAX_RETRIES):
        try:
            logger.info(f"正在下载 Singbox 配置{' (重试 ' + str(attempt) + '/' + str(MAX_RETRIES) + ')' if attempt > 0 else ''}...")
            session = requests.Session()
            session.verify = False
            headers = {"User-Agent": f"SFA/1.1{SINGBOX_VERSION} (595; sing-box {SINGBOX_VERSION}; language zh_CN)"}
            resp = session.get(SINGBOX_URL, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            config = resp.json()

            config = add_route_rules(config)

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.info(f"Singbox 配置已同步到 {OUTPUT_FILE}")

            generate_docker_config(config)
            return True
        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = (attempt + 1) * 2
                logger.warning(f"同步失败 (重试 {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(delay)
            else:
                logger.error(f"Singbox 配置同步失败 (已重试 {MAX_RETRIES} 次): {e}")
                return False


def run():
    sync()
    schedule.every().day.at("07:00").do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
