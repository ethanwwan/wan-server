import os
import sys
import json
import time
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('SYNC_TVBOX')

SOURCE_URL = "https://gh-proxy.org/https://raw.githubusercontent.com/ethanwwan/wan-server/refs/heads/main/tvbox-aggregator/output/tvbox.json"
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'tvbox.json')
MAX_RETRIES = 2


def sync_tvbox_config() -> bool:
    for attempt in range(1 + MAX_RETRIES):
        try:
            logger.info(f"正在下载 TVBox 配置{' (重试 ' + str(attempt) + '/' + str(MAX_RETRIES) + ')' if attempt > 0 else ''}...")
            resp = requests.get(SOURCE_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"TVBox 配置已同步到 {OUTPUT_FILE}")
            return True
        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = (attempt + 1) * 2
                logger.warning(f"同步失败 (重试 {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(delay)
            else:
                logger.error(f"TVBox 配置同步失败 (已重试 {MAX_RETRIES} 次): {e}")
                return False


if __name__ == "__main__":
    sync_tvbox_config()
