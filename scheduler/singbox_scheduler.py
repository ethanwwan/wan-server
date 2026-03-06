"""
Singbox配置定时更新模块
负责每8小时自动更新singbox配置文件
"""

import os
import json
import concurrent.futures
from datetime import datetime
from typing import Dict, Optional, Tuple
from utils.ip_utils import get_server_ip, get_ip_location
from utils.logger import get_logger
from config import CONFIG
import requests

# 项目根目录和配置路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'output', 'singbox')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
CONFIG_OLD_PATH = os.path.join(CONFIG_DIR, 'config_old.json')
DOCKER_CONFIG_DIR = os.path.join(CONFIG_DIR, 'docker')
DOCKER_CONFIG_PATH = os.path.join(DOCKER_CONFIG_DIR, 'config.json')

# 从配置文件读取常量
SINGBOX_URL = CONFIG.singbox.url
SINGBOX_VERSION = CONFIG.singbox.version
SINGBOX_OLD_VERSION = CONFIG.singbox.old_version
GLOBAL_RULESET_URL = CONFIG.singbox.global_ruleset_url

# 请求超时设置
REQUEST_TIMEOUT = 20
MAX_WORKERS = 10

# 日志记录器
logger = get_logger('SINGBOX')


def singbox_scheduler():
    """
    每8小时更新一次singbox配置
    
    功能：
    - 从远程URL下载最新配置
    - 保存到本地配置文件
    - 处理配置，添加国家信息到节点标签
    """
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")
    
    try:
        # 更新最新版本配置
        update_config(is_latest=True)
        # 更新旧版本配置
        update_config(is_latest=False)
        logger.info(f"配置更新成功完成，时间: {datetime.now().isoformat()}")
    except Exception as e:
        logger.error(f"调度器执行错误: {e}")


def update_config(is_latest: bool = True) -> bool:
    """
    更新配置文件
    
    Args:
        is_latest: 是否更新最新版本配置
        
    Returns:
        bool: 更新是否成功
    """
    version = SINGBOX_VERSION if is_latest else SINGBOX_OLD_VERSION
    target_config_path = CONFIG_PATH if is_latest else CONFIG_OLD_PATH
    
    headers = {"User-Agent": f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"}
    
    # 验证SINGBOX_URL是否配置
    if not SINGBOX_URL:
        logger.error("SINGBOX_URL 未配置")
        return False
    
    try:
        # 获取远程配置
        response = requests.get(SINGBOX_URL, headers=headers, verify=False, timeout=REQUEST_TIMEOUT)
        
        # 检查响应状态
        if response.status_code != 200:
            logger.error(f"请求失败: 状态码 {response.status_code}")
            return False
        
        # 检查响应内容
        if not response.text.strip():
            logger.error("请求失败: 内容为空")
            return False
        
        # 解析配置
        config = json.loads(response.text.strip())
        if not isinstance(config, dict):
            logger.error("配置解析错误: 配置不是有效的JSON对象")
            return False
        
        # 处理配置
        config = process_config(config)
        
        # 确保配置目录存在
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # 保存配置文件
        with open(target_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        # 为最新版本生成Docker配置
        if is_latest:
            generate_docker_config(config)
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"配置解析错误: {e}")
        return False
    except requests.RequestException as e:
        logger.error(f"网络请求错误: {e}")
        return False
    except Exception as e:
        logger.error(f"配置处理错误: {e}")
        return False


def generate_docker_config(config: Dict) -> None:
    """
    生成Docker环境专用配置
    
    Args:
        config: 原始配置字典
    """
    try:
        # 创建Docker配置目录
        os.makedirs(DOCKER_CONFIG_DIR, exist_ok=True)
        
        # 复制并修改配置
        docker_config = config.copy()
        inbounds = docker_config.get('inbounds', [])
        
        # 移除tun类型的入站配置
        filtered_inbounds = [inbound for inbound in inbounds if inbound.get('type') != 'tun']
        docker_config['inbounds'] = filtered_inbounds
        
        # 保存Docker配置
        with open(DOCKER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(docker_config, f, ensure_ascii=False, indent=4)
        
    except Exception as e:
        logger.error(f"生成Docker配置失败: {e}")


def process_config(config: Dict) -> Dict:
    """
    处理配置，添加路由规则和国家信息
    
    Args:
        config: 原始配置字典
        
    Returns:
        Dict: 处理后的配置字典
    """
    # 添加路由规则
    config = add_route_rules(config)
    
    # 处理出站节点，添加国家信息
    config = process_outbounds(config)
    
    return config


def add_route_rules(config: Dict) -> Dict:
    """
    添加路由规则到配置
    
    Args:
        config: 原始配置字典
        
    Returns:
        Dict: 添加路由规则后的配置字典
    """
    # 获取或创建route配置
    route = config.get('route', {})
    
    # 设置默认路由为直连
    route['final'] = "direct"
    
    # 添加Global规则集
    if 'rule_set' not in route:
        route['rule_set'] = []
    
    route['rule_set'].append({
        "tag": "Global",
        "type": "remote",
        "format": "source",
        "url": GLOBAL_RULESET_URL,
        "download_detour": "direct"
    })
    
    # 添加Global规则
    if 'rules' not in route:
        route['rules'] = []
    
    route['rules'].append({
        "rule_set": "Global",
        "outbound": "🚀 节点选择"
    })
    
    config['route'] = route
    return config


def process_outbounds(config: Dict) -> Dict:
    """
    处理出站节点，添加国家信息到标签
    
    Args:
        config: 原始配置字典
        
    Returns:
        Dict: 处理后的配置字典
    """
    outbounds = config.get('outbounds', [])
    if not outbounds:
        return config
    
    # 收集需要处理的节点信息
    nodes_to_process = []
    for i, item in enumerate(outbounds):
        item_type = item.get('type')
        server = item.get('server')
        tag = item.get('tag')
        
        if item_type in ['hysteria2', 'tuic', 'vless'] and server and tag:
            nodes_to_process.append((i, server, tag))
    
    # 并发处理节点信息
    tag_map = {}
    total_nodes = len(nodes_to_process)
    processed_nodes = 0
    
    if total_nodes > 0:
        
        # 限制并发数，避免过多线程
        max_workers = min(MAX_WORKERS, total_nodes)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_node = {
                executor.submit(get_node_country_info, server, tag): (i, tag)
                for i, server, tag in nodes_to_process
            }
            
            # 处理任务结果
            for future in concurrent.futures.as_completed(future_to_node):
                i, old_tag = future_to_node[future]
                try:
                    new_tag, ip, country = future.result()
                    processed_nodes += 1
                    if new_tag:
                        outbounds[i]['tag'] = new_tag
                        tag_map[old_tag] = new_tag
                except Exception as e:
                    processed_nodes += 1
                    logger.error(f"处理节点失败 ({processed_nodes}/{total_nodes}): {e}")
        
    
    # 更新selector和urltest类型的出站配置
    for item in outbounds:
        item_type = item.get('type')
        if item_type in ['selector', 'urltest']:
            old_outbounds = item.get('outbounds', [])
            new_outbounds = []
            updated_tags = 0
            
            for old_tag in old_outbounds:
                if old_tag in tag_map:
                    new_tag = tag_map[old_tag]
                    new_outbounds.append(new_tag)
                    updated_tags += 1
                else:
                    new_outbounds.append(old_tag)
            
            if updated_tags > 0:
                item['outbounds'] = new_outbounds
    
    return config


def get_node_country_info(server: str, tag: str) -> Tuple[Optional[str], str, Optional[str]]:
    """
    获取节点的国家信息
    
    Args:
        server: 服务器域名
        tag: 节点标签
        
    Returns:
        Tuple[Optional[str], str, Optional[str]]: (新标签, IP地址, 国家代码)
    """
    ip = get_server_ip(server)
    if not ip:
        return None, server, None
    
    country = get_ip_location(ip)
    if not country:
        return None, ip, None
    
    new_tag = f"{tag}-{country}"
    return new_tag, ip, country


def get_config_json(is_latest: bool = True) -> Dict:
    """
    获取当前配置信息
    
    Args:
        is_latest: 是否获取最新版本配置
        
    Returns:
        Dict: 配置信息字典
    """
    config_data = {}
    target_config_path = CONFIG_PATH if is_latest else CONFIG_OLD_PATH
    
    try:
        if os.path.exists(target_config_path):
            with open(target_config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"配置文件解析错误: {e}")
    except Exception as e:
        logger.error(f"获取配置信息错误: {e}")
    finally:
        return config_data


if __name__ == "__main__":
    # 测试功能
    print("=== Singbox 调度器测试 ===")
    
    # 显示当前配置信息
    print("\n--- 当前配置信息 ---")
    config = get_config_json()
    print(f"配置文件大小: {len(json.dumps(config))} 字节")
    
    # 执行配置更新
    print("\n--- 正在更新配置 ---")
    success = singbox_scheduler()
    
    print("\n=== 测试完成 ===")







