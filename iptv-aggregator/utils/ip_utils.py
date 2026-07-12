#!/usr/bin/env python3
"""
IP 解析和国家获取工具类
"""

import socket
import dns.resolver
import requests
import time
from typing import Dict, Tuple, Optional

# DNS服务器配置
DNS_SERVERS = [
    "8.8.8.8",  # Google DNS
    "8.8.4.4",  # Google DNS 备用
    "1.1.1.1",  # Cloudflare DNS
    "1.0.0.1",  # Cloudflare DNS 备用
    "208.67.222.222",  # OpenDNS
    "208.67.220.220",  # OpenDNS 备用
    "9.9.9.9",  # Quad9 DNS
    "149.112.112.112"  # Quad9 DNS 备用
]

# 请求超时设置
IP_INFO_TIMEOUT = 5
DNS_TIMEOUT = 5

# 缓存
IP_CACHE: Dict[str, str] = {}  # 缓存IP地址对应的国家信息
DNS_CACHE: Dict[str, Tuple[str, float]] = {}  # 缓存域名对应的(IP地址, 缓存时间)
CACHE_EXPIRY = 3600  # 缓存过期时间（秒）

# IP 信息 URL
IP_INFO_URL = "https://ipinfo.io/{ip}/country"

def is_valid_ipv6(ip: str) -> bool:
    """
    验证IPv6地址格式是否有效
    
    Args:
        ip: IPv6地址
        
    Returns:
        bool: 是否为有效的IPv6地址
    """
    try:
        # 尝试解析IPv6地址
        socket.inet_pton(socket.AF_INET6, ip)
        return True
    except:
        return False

def is_reserved_ip(ip: str) -> bool:
    """
    检查IP是否为保留地址
    
    Args:
        ip: IP地址
        
    Returns:
        bool: 是否为保留地址
    """
    try:
        # 检查是否为IPv6地址
        if ':' in ip:
            # IPv6地址验证
            if not is_valid_ipv6(ip):
                return True
            
            # IPv6保留地址检查
            # 暂时只检查IPv4映射的IPv6地址
            if ip.startswith('::ffff:'):
                ipv4_part = ip.split('::ffff:')[1]
                return is_reserved_ip(ipv4_part)
            
            # 其他IPv6保留地址检查可以在这里添加
            # 例如：链路本地地址 (fe80::/10)、唯一本地地址 (fc00::/7) 等
            return False
        else:
            # IPv4地址检查
            parts = list(map(int, ip.split('.')))
            if len(parts) != 4:
                return True
                
            # 检查保留地址范围
            # 198.18.0.0/15 基准测试地址
            if parts[0] == 198 and parts[1] in [18, 19]:
                return True
                
            # 其他保留地址检查
            # 0.0.0.0/8 保留地址
            if parts[0] == 0:
                return True
            # 127.0.0.0/8 回环地址
            if parts[0] == 127:
                return True
            # 169.254.0.0/16 链路本地地址
            if parts[0] == 169 and parts[1] == 254:
                return True
            # 224.0.0.0/4 多播地址
            if parts[0] >= 224:
                return True
                
            return False
    except:
        return True

def get_server_ip(server: str) -> str:
    """
    获取服务器域名对应的真实IP地址，优先返回IPv6地址
    
    Args:
        server: 服务器域名
    
    Returns:
        str: 服务器真实IP地址，如果获取失败或为保留地址则返回空字符串
    """
    
    # 检查缓存（带过期时间）
    if server in DNS_CACHE:
        cached_ip, cache_time = DNS_CACHE[server]
        if time.time() - cache_time < CACHE_EXPIRY:
            if not is_reserved_ip(cached_ip):
                return cached_ip
    
    # 收集所有解析结果，过滤掉保留地址
    resolved_ips = []
    
    # 1. 使用socket.getaddrinfo优先获取IPv6地址
    try:
        # 不指定地址族，自动获取IPv4和IPv6地址
        addrinfo = socket.getaddrinfo(server, None, 0, socket.SOCK_STREAM)
        
        # 优先处理IPv6地址
        for info in addrinfo:
            family, _, _, _, sockaddr = info
            if family == socket.AF_INET6:
                ip = sockaddr[0]
                if not is_reserved_ip(ip):
                    # 更新缓存
                    DNS_CACHE[server] = (ip, time.time())
                    return ip
        
        # 如果没有找到可用的IPv6地址，尝试IPv4地址
        for info in addrinfo:
            family, _, _, _, sockaddr = info
            if family == socket.AF_INET:
                ip = sockaddr[0]
                if not is_reserved_ip(ip):
                    # 更新缓存
                    DNS_CACHE[server] = (ip, time.time())
                    return ip
    except:
        pass
    
    # 2. 使用dnspython库进行DNS解析（优先AAAA记录）
    try:
        for dns_server in DNS_SERVERS:
            try:
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [dns_server]
                # 设置超时时间
                resolver.timeout = DNS_TIMEOUT
                resolver.lifetime = DNS_TIMEOUT
                
                # 优先解析AAAA记录（IPv6）
                try:
                    answers = resolver.resolve(server, 'AAAA')
                    for rdata in answers:
                        ip = str(rdata.address)
                        if not is_reserved_ip(ip):
                            # 更新缓存
                            DNS_CACHE[server] = (ip, time.time())
                            return ip
                except dns.resolver.NoAnswer:
                    pass
                except:
                    pass
                
                # 解析A记录（IPv4）
                try:
                    answers = resolver.resolve(server, 'A')
                    for rdata in answers:
                        ip = str(rdata.address)
                        if not is_reserved_ip(ip):
                            # 更新缓存
                            DNS_CACHE[server] = (ip, time.time())
                            return ip
                except dns.resolver.NoAnswer:
                    pass
                except:
                    pass
            except dns.resolver.NXDOMAIN:
                break  # 域名不存在，无需尝试其他DNS服务器
            except dns.resolver.Timeout:
                continue
            except:
                continue
    except ImportError:
        pass
    except:
        pass
    
    # 3. 使用默认DNS解析（IPv4）
    try:
        ip = socket.gethostbyname(server)
        if not is_reserved_ip(ip):
            # 更新缓存
            DNS_CACHE[server] = (ip, time.time())
            return ip
    except:
        pass
    
    # 所有解析都失败，返回空字符串
    return ""

def get_ip_location(ip: str) -> str:
    """
    获取IP地址对应的国家信息
    
    Args:
        ip: IP地址
    
    Returns:
        str: 国家信息，如果获取失败则返回空字符串
    """
    # 检查缓存
    if ip in IP_CACHE:
        return IP_CACHE[ip]
    
    try:
        response = requests.get(IP_INFO_URL.format(ip=ip), timeout=IP_INFO_TIMEOUT)
        if response.status_code == 200:
            country = response.text.strip().upper()
            # 缓存结果
            IP_CACHE[ip] = country
            return country
        return ""
    except:
        return ""
