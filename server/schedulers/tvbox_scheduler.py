import os
import sys
import json
import time
import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_TVBOX')

_raw = json.load(open(os.path.join(project_root, 'input', 'config.json')))
_proxies = _raw['proxy_domains']
_TIMEOUT = _raw['request_timeout']
cfg = _raw['tvbox']
SOURCE_URL = cfg['source_url']
OUTPUT_DIR = os.path.join(project_root, 'output', cfg['output_dir'])
OUTPUT_FILE = os.path.join(OUTPUT_DIR, cfg['output_file'])
SCHEDULE_TIME = cfg['schedule_time']


def _build_url(proxy_idx: int) -> str:
    return _proxies[proxy_idx] + '/' + SOURCE_URL


def sync() -> bool:
    if cfg['use_proxy']:
        attempts = list(range(len(_proxies)))
    else:
        attempts = [None]

    for idx in attempts:
        url = _build_url(idx) if idx is not None else SOURCE_URL
        label = f" (代理 {idx + 1}/{len(attempts)})" if cfg['use_proxy'] and idx > 0 else ""
        try:
            logger.info(f"正在下载 TVBox 配置{label}...")
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"TVBox 配置已同步到 {OUTPUT_FILE}")
            return True
        except Exception as e:
            is_last = idx == attempts[-1]
            logger.warning(f"同步失败{label}: {e}{', 切换代理...' if not is_last else ''}")
            if is_last:
                logger.error(f"TVBox 配置同步失败 (已用完全部代理)")
                return False


def run():
    sync()
    schedule.every().day.at(SCHEDULE_TIME).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
