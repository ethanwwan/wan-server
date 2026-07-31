"""
HTTP 下载器

封装订阅 URL 下载逻辑：
  - 统一 User-Agent
  - 关闭 SSL 校验（内网工具，订阅源证书偶尔异常）+ 抑制警告
  - 支持 JSON / YAML 解析
"""
import urllib3
import requests
import yaml
from typing import Optional

from .constants import REQUEST_TIMEOUT

# 抑制 verify=False 导致的 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _create_session() -> requests.Session:
    """创建禁用了 TLS 校验的 Session（内网订阅工具）"""
    session = requests.Session()
    session.verify = False
    return session


def fetch_json(url: str, user_agent: str, timeout: int = REQUEST_TIMEOUT) -> Optional[dict]:
    """
    下载 JSON 配置（如 sing-box）

    Returns:
        dict: 成功时返回解析后的 JSON
        None: 失败时
    """
    try:
        session = _create_session()
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"下载失败 {url}: {e}")
        return None


def fetch_yaml(url: str, user_agent: str, timeout: int = REQUEST_TIMEOUT) -> Optional[dict]:
    """
    下载 YAML 配置（如 Clash / mihomo）

    Returns:
        dict: 成功时返回解析后的 YAML
        None: 失败时
    """
    try:
        session = _create_session()
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()
        return yaml.safe_load(resp.content)
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"YAML 下载失败 {url}: {e}")
        return None


def fetch_text(url: str, user_agent: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """下载纯文本内容"""
    try:
        session = _create_session()
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.error(f"文本下载失败 {url}: {e}")
        return None


# User-Agent 模板
def singbox_user_agent(version: str) -> str:
    """sing-box 订阅 User-Agent"""
    return f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"


def clash_user_agent() -> str:
    """Clash / mihomo 订阅 User-Agent"""
    return "clash-verge/2.0.0"