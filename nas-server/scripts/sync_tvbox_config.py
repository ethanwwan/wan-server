import os
import sys
import requests

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from logger import get_logger

logger = get_logger('SYNC_TVBOX')

SOURCE_URL = "https://gh-proxy.org/https://github.com/ethanwwan/wan-server/blob/main/tvbox-aggregator/output/config.json"
OUTPUT_DIR = os.path.join(project_root, 'nas-server', 'output')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'tvbox.json')


def sync_tvbox_config() -> bool:
    try:
        logger.info(f"正在下载 TVBox 配置...")
        resp = requests.get(SOURCE_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            import json
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"TVBox 配置已同步到 {OUTPUT_FILE}")
        return True
    except Exception as e:
        logger.error(f"TVBox 配置同步失败: {e}")
        return False


if __name__ == "__main__":
    sync_tvbox_config()
