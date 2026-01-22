"""
IPTV NAS M3U配置文件工具模块
提供获取IPTV NAS M3U配置文件内容的功能
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import os
import re
from datetime import datetime
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

m3u_url = "http://192.168.1.12:8032/static/output/playlist.m3u"

def fetch_iptv_nas_playlist():
    """
    获取IPTV NAS M3U配置文件内容
    """
    return requests.get(m3u_url, verify=False, timeout=12).text.strip()
