"""
Docker 容器专用 sing-box 配置处理

与正常客户端配置的差异：
  1. 移除 tun inbound（容器内无 /dev/net/tun）
  2. 移除 socks inbound（避免与 mixed 端口冲突）
  3. 移除 DNS server 的 detour（避免启动时 DNS 死锁）
  4. 强制使用国内 DNS 作为 default_domain_resolver
"""
import copy
from typing import Optional


def process(config: dict) -> dict:
    """
    处理 sing-box 配置用于 docker 容器

    Args:
        config: 已通过 singbox_builder.process() 处理过的配置

    Returns:
        深拷贝的新配置（不修改原对象）
    """
    config = copy.deepcopy(config)

    # 1. 移除 tun inbound
    inbounds = config.get('inbounds', [])
    inbounds[:] = [
        ib for ib in inbounds
        if isinstance(ib, dict) and ib.get('type') != 'tun'
    ]

    # 2. 移除 socks inbound（mixed 已支持 socks 协议）
    has_mixed = any(
        isinstance(ib, dict) and ib.get('type') == 'mixed'
        for ib in inbounds
    )
    socks_removed = 0
    if has_mixed:
        socks_removed = sum(1 for ib in inbounds if isinstance(ib, dict) and ib.get('type') == 'socks')
        inbounds[:] = [
            ib for ib in inbounds
            if not (isinstance(ib, dict) and ib.get('type') == 'socks')
        ]

    # 3. 移除 DNS server 的 detour（避免 DNS 死锁）
    dns = config.get('dns')
    if isinstance(dns, dict):
        for srv in dns.get('servers', []):
            if isinstance(srv, dict) and 'detour' in srv:
                del srv['detour']

    # 4. 强制使用国内 DNS 作为 default_domain_resolver
    preferred_dns_tag = None
    if isinstance(dns, dict):
        preferred_keywords = ['223.5.5.5', '119.29.29.29', 'ali_dns', 'dns_local',
                              'doh.pub', 'local']
        for srv in dns.get('servers', []):
            if not isinstance(srv, dict):
                continue
            tag = srv.get('tag', '').lower()
            server = str(srv.get('server', ''))
            for kw in preferred_keywords:
                if kw in tag or kw in server:
                    preferred_dns_tag = srv.get('tag')
                    break
            if preferred_dns_tag:
                break

    if preferred_dns_tag:
        route = config.setdefault('route', {})
        route['default_domain_resolver'] = {'server': preferred_dns_tag}

    # 日志
    from logger import get_logger
    logger = get_logger('NAS_PROXY')
    if socks_removed:
        logger.info(f"Docker 配置: 已移除 {socks_removed} 个 socks inbound (避免端口冲突)")
    logger.info(f"Docker 配置: 剩余 {len(inbounds)} 个 inbound ({[ib.get('type') for ib in inbounds]})")
    if preferred_dns_tag:
        logger.info(f"Docker 配置: default_domain_resolver → {preferred_dns_tag} (国内 DNS)")

    return config