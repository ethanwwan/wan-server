import os
import sys
import json
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from logger import get_logger

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'tvbox.json')
INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'input', 'tvbox_urls.json')
HEADERS = {"User-Agent": "okhttp/3.12.12", "Accept": "application/json"}
MAX_WORKERS = 10
REPLACE_KEYWORDS = ['csp_DouDouGuard', 'csp_Douban', 'csp_DouDou', 'csp_DoubanGuard']

logger = get_logger('TVBOX')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_sources() -> dict:
    if not os.path.exists(INPUT_FILE):
        logger.error(f"配置文件不存在: {INPUT_FILE}")
        return {}
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _fetch_raw(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.content.decode('utf-8-sig')
    except Exception:
        return None


def _clean(content_str: str) -> dict | None:
    if not content_str.strip():
        return None
    try:
        data = json.loads(content_str)
    except json.JSONDecodeError:
        try:
            cleaned = re.sub(r'/\*.*?\*/', '', content_str, flags=re.DOTALL)
            lines = cleaned.split('\n')
            cleaned = '\n'.join(line for line in lines if not line.lstrip().startswith('//'))
            cleaned = ' '.join(cleaned.split())
            data = json.loads(cleaned)
        except (json.JSONDecodeError, Exception):
            return None

    sites = data.get('sites', [])
    if not sites:
        logger.warning("未检测到 sites 字段，跳过")
        return None

    if 'warningText' in data:
        del data['warningText']

    new_name = "🚀豆瓣┃热播"
    for site in sites:
        api_key = site.get('api', '')
        if api_key == "push_agent":
            sites.remove(site)
            continue
        for keyword in REPLACE_KEYWORDS:
            if keyword == api_key:
                site['name'] = new_name
                break

    return data


def _process_source(name: str, urls: list[str]) -> dict | None:
    for url in urls:
        logger.info(f"正在尝试 [{name}] {url}")
        raw = _fetch_raw(url)
        if raw is None:
            logger.warning(f"[{name}] 获取失败: {url}")
            continue

        data = _clean(raw)
        if data is None:
            logger.warning(f"[{name}] 内容解析失败: {url}")
            continue

        logger.info(f"[{name}] 处理成功")
        return data

    logger.warning(f"[{name}] 所有 URL 均失败，跳过")
    return None


def _merge(results: list[dict]) -> dict:
    merged = {}
    for data in results:
        for key, value in data.items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
            elif key not in merged:
                merged[key] = value
    return merged


def tvbox_scheduler():
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")

    sources = load_sources()
    if not sources:
        logger.error("未读取到任何源配置")
        return

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_process_source, name, urls): name for name, urls in sources.items()}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        logger.warning("没有成功处理任何源")
        return

    data = _merge(results)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"配置更新完成，成功: {len(results)}/{len(sources)}，输出: {OUTPUT_FILE}")


if __name__ == "__main__":
    tvbox_scheduler()
