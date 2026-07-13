import os
import sys
import json
import requests
import re
import base64
from datetime import datetime
from urllib.parse import urljoin

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from logger import get_logger

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'tvbox.json')
INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'input', 'tvbox_urls.json')
HEADERS = {"User-Agent": "okhttp/3.12.12", "Accept": "application/json"}
JAR_HEADERS = {"User-Agent": "okhttp/3.12.12"}
REPLACE_KEYWORDS = ['csp_DouDouGuard', 'csp_Douban', 'csp_DouDou', 'csp_DoubanGuard']

logger = get_logger('TVBOX')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_sources() -> dict:
    if not os.path.exists(INPUT_FILE):
        logger.error(f"配置文件不存在: {INPUT_FILE}")
        return {}
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _extract_real_url(source_url: str) -> str:
    m = re.match(r'(https?://[^/]+/)(?:https?://.*)', source_url)
    if m:
        real = source_url[len(m.group(1)):]
        if real.startswith('http://') or real.startswith('https://'):
            return real
    return source_url


def _extract_jar_url(data: dict, source_url: str) -> str | None:
    spider = data.get('spider', '')
    if not spider or not spider.strip():
        return None
    jar_path = spider.split(';')[0].strip()
    if not jar_path:
        return None
    if jar_path.startswith('http://') or jar_path.startswith('https://'):
        return jar_path
    real_url = _extract_real_url(source_url)
    return urljoin(real_url, jar_path)


def _jar_reachable(url: str, timeout: int = 5) -> bool:
    for method in ('HEAD', 'GET'):
        try:
            resp = requests.request(method, url, headers=JAR_HEADERS,
                                    timeout=timeout, allow_redirects=True)
            if resp.ok:
                return True
        except Exception:
            continue
    return False


def _decode_response(body: bytes) -> str | None:
    text = body.decode('utf-8', errors='replace')
    try:
        if text.strip().startswith('{'):
            json.loads(text)
            return text
    except json.JSONDecodeError:
        pass
    m = re.search(r'[A-Za-z0-9]{8}\*\*', text)
    if not m:
        return None
    after = text[text.index(m.group()) + 10:]
    try:
        decoded = base64.b64decode(after)
        return decoded.decode('utf-8', errors='replace')
    except Exception:
        return None


def _fetch_raw(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        body = resp.content
        decoded = _decode_response(body)
        if decoded:
            return decoded
        return body.decode('utf-8-sig')
    except Exception:
        return None


def _parse_json(content_str: str) -> dict | None:
    if not content_str.strip():
        return None
    try:
        return json.loads(content_str)
    except json.JSONDecodeError:
        pass
    try:
        cleaned = re.sub(r'/\*.*?\*/', '', content_str, flags=re.DOTALL)
        lines = cleaned.split('\n')
        cleaned = '\n'.join(line for line in lines if not line.lstrip().startswith('//'))
        cleaned = ' '.join(cleaned.split())
        return json.loads(cleaned)
    except Exception:
        return None


def _clean_data(data: dict) -> dict | None:
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
        else:
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

        data = _parse_json(raw)
        if data is None:
            logger.warning(f"[{name}] JSON 解析失败: {url}")
            continue

        jar_url = _extract_jar_url(data, url)
        if jar_url is not None:
            logger.info(f"[{name}] 检测 jar: {jar_url}")
            if not _jar_reachable(jar_url):
                logger.warning(f"[{name}] jar 不可达，尝试下一个 URL")
                continue
            logger.info(f"[{name}] jar 可用")

        data = _clean_data(data)
        if data is None:
            logger.warning(f"[{name}] 内容清洗失败（无 sites）: {url}")
            continue

        logger.info(f"[{name}] 处理成功")
        return data

    logger.warning(f"[{name}] 所有 URL 均失败，跳过")
    return None


def tvbox_scheduler():
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")

    sources = load_sources()
    if not sources:
        logger.error("未读取到任何源配置")
        return

    for name, urls in sources.items():
        data = _process_source(name, urls)
        if data:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"配置更新完成，使用源: [{name}]，输出: {OUTPUT_FILE}")
            return

    logger.warning("所有源均失败")


if __name__ == "__main__":
    tvbox_scheduler()
