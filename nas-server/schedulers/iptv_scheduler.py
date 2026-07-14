import os
import sys
import time
import schedule
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('NAS_IPTV')

SOURCE_URL = "https://gh-proxy.org/https://raw.githubusercontent.com/ethanwwan/wan-server/refs/heads/main/iptv-aggregator/output/playlist.m3u"
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output', 'iptv')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'playlist.m3u')
MAX_RETRIES = 2


def sync() -> bool:
    for attempt in range(1 + MAX_RETRIES):
        try:
            logger.info(f"正在下载 IPTV 配置{' (重试 ' + str(attempt) + '/' + str(MAX_RETRIES) + ')' if attempt > 0 else ''}...")
            resp = requests.get(SOURCE_URL, timeout=30)
            resp.raise_for_status()
            content = resp.text

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"IPTV 配置已同步到 {OUTPUT_FILE}")
            return True
        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = (attempt + 1) * 2
                logger.warning(f"同步失败 (重试 {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(delay)
            else:
                logger.error(f"IPTV 配置同步失败 (已重试 {MAX_RETRIES} 次): {e}")
                return False


def run():
    sync()
    schedule.every().day.at("06:30").do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
