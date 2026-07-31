"""
DNS 解析

三级降级策略：
  1. socket.getaddrinfo（走系统 DNS，docker 内走容器 /etc/resolv.conf）
  2. UDP 并发查询 4 个公共 DNS（Google/Cloudflare/阿里/Quad9）
  3. 返回 None
"""
import socket
import concurrent.futures
from typing import Optional

from .constants import FALLBACK_DNS_SERVERS


def _dns_udp_query(dns_server: str, hostname: str) -> Optional[str]:
    """使用 dnspython 通过指定 DNS 服务器解析域名（UDP）"""
    try:
        import dns.resolver  # 可选依赖
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [dns_server]
        resolver.timeout = 2
        resolver.lifetime = 2
        answers = resolver.resolve(hostname, 'A')
        for a in answers:
            if a.rdtype == 1:
                return a.to_text()
    except Exception:
        return None
    return None


def resolve(hostname: str, log_warning: bool = True) -> Optional[str]:
    """
    多级降级 DNS 解析

    Returns:
        IP 地址字符串；解析失败返回 None
    """
    # 阶段 1: 系统 getaddrinfo（走 docker 容器本地 DNS，最快最稳）
    try:
        socket.setdefaulttimeout(3)
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass

    # 阶段 2: UDP 并发查询 4 个公共 DNS（系统 DNS 失败时降级）
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futs = {
                executor.submit(_dns_udp_query, dns, hostname): dns
                for dns in FALLBACK_DNS_SERVERS
            }
            for fut in concurrent.futures.as_completed(futs):
                ip = fut.result()
                if ip:
                    return ip
    except Exception:
        pass

    if log_warning:
        from logger import get_logger
        logger = get_logger('NAS_PROXY')
        logger.warning(f"DNS 解析失败 {hostname}: 所有方法均不可用")
    return None