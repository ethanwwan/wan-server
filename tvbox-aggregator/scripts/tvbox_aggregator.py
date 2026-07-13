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

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'tvbox.json')
INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'input', 'tvbox_urls.json')
HEADERS = {"User-Agent": "okhttp/3.12.12", "Accept": "application/json"}
MAX_WORKERS = 10
REPLACE_KEYWORDS = ['csp_DouDouGuard', 'csp_Douban', 'csp_DouDou', 'csp_DoubanGuard']

logger = get_logger('TVBOX')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_sources() -> dict:
    """读取 tvbox_urls.json 配置"""
    if not os.path.exists(INPUT_FILE):
        logger.error(f"配置文件不存在: {INPUT_FILE}")
        return {}
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _fetch_and_format(url: str) -> bytes | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        content = _format_content(resp.content)
        if content and len(content) > 0:
            return content
    except Exception:
        pass
    return None


def _process_source(name: str, urls: list[str]) -> dict | None:
    """
    处理一个源：依次尝试 URL 列表，第一个成功则停止
    返回带 name/url 的 item，全部失败返回 None
    """
    for url in urls:
        logger.info(f"正在尝试 [{name}] {url}")
        raw = _fetch_and_format(url)
        if raw is None:
            logger.warning(f"[{name}] 获取失败: {url}")
            continue

        final = _replace_content(raw)
        if final is None:
            logger.warning(f"[{name}] 内容解析失败: {url}")
            continue

        item = {
            'name': name.replace('游魂', '万家'),
            'url': url
        }
        logger.info(f"[{name}] 处理成功")
        return item

    logger.warning(f"[{name}] 所有 URL 均失败，跳过")
    return None


def _format_content(content: bytes) -> bytes | None:
    """将原始响应内容格式化为标准 JSON"""
    try:
        content_str = content.decode('utf-8-sig')
        if not content_str.strip():
            return None

        try:
            data = json.loads(content_str)
            return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r'/\*.*?\*/', '', content_str, flags=re.DOTALL)
                lines = cleaned.split('\n')
                cleaned = '\n'.join(line for line in lines if not line.lstrip().startswith('//'))
                cleaned = ' '.join(cleaned.split())
                data = json.loads(cleaned)
                return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            except json.JSONDecodeError:
                return None
    except Exception:
        return None


def _replace_content(content: bytes) -> bytes | None:
    """替换内容中的关键词"""
    try:
        data = json.loads(content)
        sites = data.get('sites', [])

        if not sites:
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

        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    except Exception:
        return None


def tvbox_scheduler():
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")

    sources = load_sources()
    if not sources:
        logger.error("未读取到任何源配置")
        return

    items = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_process_source, name, urls): name for name, urls in sources.items()}
        for future in as_completed(futures):
            result = future.result()
            if result:
                items.append(result)

    if items:
        data = {'urls': items}
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"配置更新完成，成功: {len(items)}/{len(sources)}，输出: {OUTPUT_FILE}")
    else:
        logger.warning("没有成功处理任何源")


if __name__ == "__main__":
    tvbox_scheduler()
