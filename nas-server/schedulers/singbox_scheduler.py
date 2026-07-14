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
cfg = _config['singbox']
SINGBOX_URL = cfg['source_url']
SINGBOX_VERSION = cfg['version']
GLOBAL_RULESET_URL = cfg['global_ruleset_url']
GEOIP_CN_URL = cfg['geoip_cn_url']
GEOSITE_CN_URL = cfg['geosite_cn_url']
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output', cfg['output_dir'])
OUTPUT_FILE = os.path.join(OUTPUT_DIR, cfg['output_file'])
DOCKER_DIR = os.path.join(project_root, 'nas-server', 'output', cfg['docker_output_dir'])
DOCKER_FILE = os.path.join(DOCKER_DIR, cfg['docker_output_file'])
SCHEDULE_TIME = cfg['schedule_time']
MAX_RETRIES = _config['max_retries']
REQUEST_TIMEOUT = cfg['request_timeout']


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
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
