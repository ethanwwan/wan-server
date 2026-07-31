"""
节点协议感知探测

按节点 type 分流：
  - hysteria2 / tuic (QUIC)  → UDP 探测
  - vless/vmess/trojan/ss/... → TCP 探测

特点：
  - 全量探测（所有节点，不抽样）
  - 并发执行（ThreadPoolExecutor）
  - 短路返回（任意一个通过即取消未启动探测）
"""
import socket
import concurrent.futures
from typing import Dict, List, Tuple, Optional

from .constants import PROBE_TIMEOUT, UDP_PROXY_TYPES, TCP_PROXY_TYPES


def _tcp_probe(server: str, port: int = 443, timeout: float = PROBE_TIMEOUT) -> bool:
    """TCP 端口连通性探测（不发送数据，只建立连接）"""
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
        if not infos:
            return False
        ip = infos[0][4][0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        finally:
            sock.close()
    except Exception:
        return False


def _udp_probe(server: str, port: int = 443, timeout: float = PROBE_TIMEOUT) -> bool:
    """UDP 端口可达性探测（用于 hysteria2 / tuic 等 QUIC 协议节点）

    原理：通过 connect() 将 UDP socket 关联到目标地址，这样内核会把收到的
    ICMP Port Unreachable / Network Unreachable / Host Unreachable 等错误
    以 ConnectionRefusedError / OSError 形式投递给下一次 send/recv。

    判定规则：
      - recv 收到 UDP 响应 → False（端口在响应非预期包，不算 hysteria2）
      - ConnectionRefusedError → False（明确收到 ICMP Port Unreachable，端口未监听）
      - 其他 OSError → False（IP 层不可达）
      - socket.timeout → True（未收到任何响应，视为网络层可达）
        注：防火墙静默丢包也会走到这里，因此本探测存在"防火墙假阳性"
    """
    sock = None
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(server, port, type=socket.SOCK_DGRAM)
        if not infos:
            return False
        ip = infos[0][4][0]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))  # connect 后内核关联 ICMP 错误
        sock.send(b'\x00')

        try:
            data = sock.recv(64)
            return False  # 收到任何 UDP 响应都算"协议不对"
        except socket.timeout:
            return True     # 超时 = 视为可达
    except ConnectionRefusedError:
        return False        # ICMP Port Unreachable
    except OSError:
        return False        # 其他网络错误
    except Exception:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _classify_nodes(nodes: List[dict]) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    """
    按节点 type 分类为 UDP/TCP 探测列表

    Returns:
        (udp_nodes, tcp_nodes) — 每个元素是 (server, port)
    """
    udp_nodes = []
    tcp_nodes = []
    for node in nodes:
        ntype = node.get('type')
        server = node.get('server')
        port = node.get('port') or node.get('server_port') or 443
        if not server:
            continue
        if ntype in UDP_PROXY_TYPES:
            udp_nodes.append((server, port))
        elif ntype in TCP_PROXY_TYPES:
            tcp_nodes.append((server, port))
    return udp_nodes, tcp_nodes


def probe_nodes(nodes: List[dict], timeout: float = PROBE_TIMEOUT) -> Tuple[bool, int, int]:
    """
    全量探测节点可用性（任意一个通过即短路返回）

    Args:
        nodes: 节点列表（每个需含 type/server/port 或 server_port）

    Returns:
        (是否可用, 已发现的可用数, 节点总数)
    """
    udp_nodes, tcp_nodes = _classify_nodes(nodes)
    all_nodes = udp_nodes + tcp_nodes
    if not all_nodes:
        return True, 0, 0

    available = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_nodes)) as executor:
        futs = {}
        for srv, port in udp_nodes:
            futs[executor.submit(_udp_probe, srv, port, timeout)] = ('udp', srv)
        for srv, port in tcp_nodes:
            futs[executor.submit(_tcp_probe, srv, port, timeout)] = ('tcp', srv)

        for fut in concurrent.futures.as_completed(futs):
            if fut.result():
                available += 1
                # 短路：取消所有未启动的探测
                for pending in futs:
                    pending.cancel()
                break

    return available >= 1, available, len(all_nodes)


def probe_clash_nodes(proxy_nodes: List[dict], timeout: float = PROBE_TIMEOUT) -> Tuple[bool, int, int, int, int]:
    """
    Clash 节点探测（带 UDP/TCP 分布统计）

    Returns:
        (是否可用, 已发现可用数, 节点总数, udp节点数, tcp节点数)
    """
    udp_nodes, tcp_nodes = _classify_nodes(proxy_nodes)
    all_nodes = udp_nodes + tcp_nodes
    if not all_nodes:
        return True, 0, 0, 0, 0

    available = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_nodes)) as executor:
        futs = {}
        for srv, port in udp_nodes:
            futs[executor.submit(_udp_probe, srv, port, timeout)] = ('udp', srv)
        for srv, port in tcp_nodes:
            futs[executor.submit(_tcp_probe, srv, port, timeout)] = ('tcp', srv)

        for fut in concurrent.futures.as_completed(futs):
            if fut.result():
                available += 1
                for pending in futs:
                    pending.cancel()
                break

    return available >= 1, available, len(all_nodes), len(udp_nodes), len(tcp_nodes)


def get_probe_stats(proxy_nodes: List[dict]) -> Dict[str, int]:
    """获取探测分布统计（用于日志展示）"""
    udp_nodes, tcp_nodes = _classify_nodes(proxy_nodes)
    return {
        'udp': len(udp_nodes),
        'tcp': len(tcp_nodes),
        'total': len(udp_nodes) + len(tcp_nodes),
    }