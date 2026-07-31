"""
通用文本/JSON 下载器（用于 IPTV / TVBox 等简单同步场景）

与 http_downloader 的区别：
  - 不返回解析后的 dict，直接返回原始 bytes / str
  - 用于 IPTV 的 m3u 文本、TVBox 的 JSON 等"原样保存"场景
"""
import urllib3
import requests
from typing import Optional, Union

from .constants import REQUEST_TIMEOUT

# 抑制 verify=False 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _create_session() -> requests.Session:
    session = requests.Session()
    session.verify = False
    return session


def fetch_bytes(
    url: str,
    user_agent: str = '',
    timeout: int = REQUEST_TIMEOUT,
) -> Optional[bytes]:
    """下载原始字节"""
    try:
        session = _create_session()
        headers = {"User-Agent": user_agent} if user_agent else {}
        resp = session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"下载失败 {url}: {e}")
        return None


def fetch_text(
    url: str,
    user_agent: str = '',
    timeout: int = REQUEST_TIMEOUT,
) -> Optional[str]:
    """下载文本内容"""
    try:
        session = _create_session()
        headers = {"User-Agent": user_agent} if user_agent else {}
        resp = session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"文本下载失败 {url}: {e}")
        return None


def fetch_json_text(
    url: str,
    user_agent: str = '',
    timeout: int = REQUEST_TIMEOUT,
) -> Optional[dict]:
    """下载 JSON（返回已解析的 dict）"""
    try:
        session = _create_session()
        headers = {"User-Agent": user_agent} if user_agent else {}
        resp = session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"JSON 下载失败 {url}: {e}")
        return None