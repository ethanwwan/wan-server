"""
IP 地理位置与节点国家代码推断

提供三层降级：
  1. 在线 IP 定位服务（ipinfo.io / ip-api.com）
  2. 从域名 / tag 推断国家代码（基于国家代码映射表）
  3. 返回 None
"""
import re
import ipaddress
import requests
from typing import Optional

from .constants import (
    REQUEST_TIMEOUT, FLAG_TO_CODE, PREFIX_MAP, ZH_KEYWORDS,
)


def get_ip_country(ip: str) -> Optional[str]:
    """
    通过 IP 定位获取国家代码（仅当 IP 不是 fakeip 段时有效）

    FakeIP 段：198.18.0.0/15（IANA 保留），所有 IP 定位服务都会拒绝
    """
    # FakeIP 段直接返回 None
    try:
        if ipaddress.ip_address(ip) in ipaddress.ip_network('198.18.0.0/15'):
            return None
    except ValueError:
        return None

    # ipinfo.io
    try:
        resp = requests.get(
            f"https://ipinfo.io/{ip}/country",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        country = resp.text.strip()
        if country:
            return country
    except Exception:
        pass

    # ip-api.com 兜底
    try:
        resp = requests.get(
            f"https://ip-api.com/json/{ip}?fields=countryCode",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success":
            return data["countryCode"]
    except Exception:
        pass

    return None


def infer_from_server(server: str, tag: str) -> Optional[str]:
    """
    从 server 域名 / 节点 tag 推断国家代码（3 级降级）

    优先级：
      1. tag 中已有的国旗 emoji
      2. server 域名前缀
      3. tag 文本中的国家关键词
    """
    # 1. 国旗 emoji
    for flag, code in FLAG_TO_CODE.items():
        if flag in tag:
            return code

    # 2. server 域名前缀
    server_lower = server.lower()
    first_part = re.split(r'[.\-_]', server_lower)[0]
    if first_part in PREFIX_MAP:
        return PREFIX_MAP[first_part]
    for prefix in sorted(PREFIX_MAP.keys(), key=len, reverse=True):
        if first_part.startswith(prefix):
            return PREFIX_MAP[prefix]

    # 3. 中文关键词（优先于英文，避免短前缀误判）
    for keyword, code in sorted(ZH_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in tag:
            return code

    # 4. 英文关键词
    tag_lower = tag.lower()
    for prefix in sorted(PREFIX_MAP.keys(), key=len, reverse=True):
        if prefix in tag_lower:
            return PREFIX_MAP[prefix]

    return None