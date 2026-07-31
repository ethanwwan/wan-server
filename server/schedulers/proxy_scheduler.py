"""
Proxy Scheduler - 代理配置同步器（编排层）

职责：
  1. 编排 sing-box 配置下载与处理
  2. 编排 Clash 配置下载与处理
  3. 管理调度循环

核心功能实现已抽取到 server/utils/：
  - http_downloader: HTTP/YAML/JSON 下载
  - dns_resolver: DNS 解析
  - node_probe: 节点协议感知探测（TCP/UDP）
  - geo_locator: IP 地理位置 + 国家代码推断
  - singbox_builder: sing-box 配置构建
  - clash_builder: Clash 配置构建
  - docker_singbox: docker 容器配置适配
  - constants: 常量与配置加载
"""
import os
import time
import json
import yaml
import schedule
from typing import Dict, Optional

from logger import get_logger

from server.utils.constants import (
    load_config, REQUEST_INTERVAL,
    build_proxy_urls, build_singbox_versions,
    get_project_root,
)
from server.utils.http_downloader import (
    fetch_json, fetch_yaml,
    singbox_user_agent, clash_user_agent,
)
from server.utils.node_probe import probe_nodes, probe_clash_nodes
from server.utils.singbox_builder import (
    add_country_tags as singbox_add_country_tags,
    process as singbox_process,
)
from server.utils.clash_builder import process as clash_process
from server.utils.docker_singbox import process as docker_singbox_process

logger = get_logger('NAS_PROXY')


# ============================================================
# 全局缓存（避免重复 DNS/IP 查询）
# ============================================================

class SharedCache:
    """跨流程共享的 DNS 解析 + 国家代码缓存"""
    def __init__(self):
        self.ip_cache: Dict[str, Optional[str]] = {}
        self.country_cache: Dict[str, Optional[str]] = {}


# ============================================================
# 块 1: Singbox 下载与处理
# ============================================================

def download_singbox(
    version: str,
    file_name: str,
    proxy_urls: list,
    output_dir: str,
    cache: SharedCache,
    cfg_proxy: dict,
    start_idx: int = 0,
) -> int:
    """
    下载 Singbox 配置（支持 url1/url2/url3 切换）

    Returns:
        成功使用的 URL 索引（>=0），失败返回 -1
    """
    user_agent = singbox_user_agent(version)

    for idx in range(start_idx, len(proxy_urls)):
        url = proxy_urls[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Singbox v{version} ({url_label})...")

        config = fetch_json(url, user_agent)
        if config is None:
            logger.warning(f"Singbox {url_label} 下载失败，尝试下一个 URL")
            continue

        # 模块 A: URL 可用性检测（协议感知 + 短路返回）
        outbounds = config.get('outbounds', [])
        available, avail_cnt, total_cnt = probe_nodes(outbounds)
        if available:
            logger.info(f"URL 可用性检测: {avail_cnt}/{total_cnt} 节点协议可达（短路）")
        else:
            logger.warning(f"Singbox {url_label} 全部节点协议不可达，尝试下一个 URL")
            continue

        # 模块 B: 添加国家标签（独立、失败不影响主流程）
        singbox_add_country_tags(
            config,
            ip_cache=cache.ip_cache,
            country_cache=cache.country_cache,
        )

        # 模块 C: 处理配置（迁移 + 标准化 + 规则）
        ruleset_url = cfg_proxy['singbox_proxy_ruleset']
        geoip_cn = cfg_proxy['singbox_geoip_cn']
        geosite_cn = cfg_proxy['singbox_geosite_cn']
        fixed_port = cfg_proxy.get('fixed_listen_port', 7890)
        config = singbox_process(config, ruleset_url, geoip_cn, geosite_cn, fixed_port=fixed_port)

        # 保存主配置
        file_path = os.path.join(output_dir, file_name)
        os.makedirs(output_dir, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"Singbox 已同步到 {file_path}")

        # 仅最新版同步 docker 副配置
        if file_name == cfg_proxy['singbox_output_filename']:
            docker_dir = os.path.join(output_dir, 'docker')
            docker_path = os.path.join(docker_dir, 'config.json')
            os.makedirs(docker_dir, exist_ok=True)
            docker_config = docker_singbox_process(config)
            with open(docker_path, 'w', encoding='utf-8') as f:
                json.dump(docker_config, f, ensure_ascii=False, indent=4)
            logger.info(f"已同步 docker 配置到 {docker_path}")

        return idx

    logger.error(f"Singbox v{version} 所有 URL 同步失败")
    return -1


# ============================================================
# 块 2: Clash 下载与处理
# ============================================================

def download_clash(
    proxy_urls: list,
    output_dir: str,
    cache: SharedCache,
    proxies: list,
    cfg_proxy: dict,
    start_idx: int = 0,
) -> bool:
    """下载 Clash 配置（支持 url1/url2/url3 切换）"""
    user_agent = clash_user_agent()

    for idx in range(start_idx, len(proxy_urls)):
        url = proxy_urls[idx]
        url_label = f"url{idx + 1}"
        logger.info(f"正在下载 Clash ({url_label})...")

        config = fetch_yaml(url, user_agent)
        if config is None:
            logger.warning(f"Clash {url_label} 下载失败，尝试下一个 URL")
            continue

        # URL 可用性检测
        proxy_nodes = config.get('proxies', [])
        available, avail_cnt, total_cnt, udp_n, tcp_n = probe_clash_nodes(proxy_nodes)
        if not available:
            logger.warning(f"Clash {url_label} URL 可用性检测失败，尝试下一个 URL")
            continue

        logger.info(
            f"Clash URL 可用性检测: {avail_cnt}/{total_cnt} 节点协议可达 "
            f"(UDP:{udp_n} TCP:{tcp_n}, 短路)"
        )

        # 处理配置
        config = clash_process(
            config,
            proxies=proxies,
            ip_cache=cache.ip_cache,
            country_cache=cache.country_cache,
        )

        # 保存
        file_path = os.path.join(output_dir, cfg_proxy['clash_output_filename'])
        os.makedirs(output_dir, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f"Clash ({url_label}) 已同步到 {file_path}")
        return True

    logger.error("Clash 所有 URL 同步失败")
    return False


# ============================================================
# 同步入口
# ============================================================

def sync() -> bool:
    """
    同步所有代理配置

    流程：
      1. 加载配置 + 初始化共享缓存
      2. 块 1：Singbox（最新 + 兼容版）
      3. 块 2：Clash 配置
    """
    raw = load_config()
    cfg_proxy = raw['proxy']
    proxies = raw['proxy_domains']
    output_dir = os.path.join(get_project_root(), 'server', 'output', cfg_proxy['output_dir'])

    cache = SharedCache()
    success_count = 0
    start_idx = 0

    # 块 1: Singbox（多个版本）
    for i, (version, filename) in enumerate(build_singbox_versions(cfg_proxy)):
        if i > 0:
            logger.info(f"等待 {REQUEST_INTERVAL} 秒后继续...")
            time.sleep(REQUEST_INTERVAL)

        result = download_singbox(
            version, filename,
            proxy_urls=build_proxy_urls(cfg_proxy),
            output_dir=output_dir,
            cache=cache,
            cfg_proxy=cfg_proxy,
            start_idx=start_idx,
        )
        if result >= 0:
            success_count += 1
            start_idx = result
        else:
            start_idx = 0

    # 块 2: Clash
    logger.info(f"等待 {REQUEST_INTERVAL} 秒后下载 Clash 配置...")
    time.sleep(REQUEST_INTERVAL)
    if download_clash(
        proxy_urls=build_proxy_urls(cfg_proxy),
        output_dir=output_dir,
        cache=cache,
        proxies=proxies,
        cfg_proxy=cfg_proxy,
        start_idx=start_idx,
    ):
        success_count += 1

    if success_count > 0:
        return True
    logger.error("Proxy 全部版本同步失败")
    return False


# ============================================================
# 调度入口
# ============================================================

def run():
    """运行调度器：立即执行一次 + 每天定时执行"""
    raw = load_config()
    cfg_proxy = raw['proxy']
    schedule_time = cfg_proxy['schedule_time']

    sync()
    schedule.every().day.at(schedule_time).do(sync)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()