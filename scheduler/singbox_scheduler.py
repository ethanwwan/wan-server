"""
Singbox配置定时更新模块
负责每8小时自动更新singbox配置文件
"""

import requests
import json
import os
from datetime import datetime
import urllib3

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 写入本地 config.json，使用 UTF-8 编码，保存到项目根目录下的public/singbox目录
# 项目根目录是包含main.py的目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_dir = os.path.join(project_root, 'public', 'singbox')
config_path = os.path.join(config_dir, 'config.json')
config_old_path = os.path.join(config_dir, 'config_old.json')

url = "https://47.238.198.94/iv/verify_mode.htm?token=9a49f8e2abcce3a0d3fd12e072065cdd"

singbox_version = "1.12.14"
singbox_old_version = "1.11.15"

def singbox_scheduler():
    """
    每8小时更新一次singbox配置
    
    功能：
    - 从远程URL下载最新配置
    - 保存到本地配置文件
    - 可选：重启singbox服务
    """
    print(f"[Singbox] 开始更新配置，时间: {datetime.now().isoformat()}")
    
    update_config(is_latest=True)
    update_config(is_latest=False)
    
    print(f"[Singbox] 配置更新成功完成，时间: {datetime.now().isoformat()}")
    
 


def update_config(is_latest: bool = True):
    """更新配置"""

    version = singbox_version if is_latest else singbox_old_version

    headers = {"User-Agent": f"SFA/1.1{version} (595; sing-box {version}; language zh_CN)"}

    try:
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        if response.status_code == 200 and response.text.strip():
            # 直接解析response.text作为完整的singbox配置JSON
            config = json.loads(response.text.strip())      
            config = replace_config(config)

            # 确保public/singbox目录存在
            os.makedirs(config_dir, exist_ok=True)

            # 根据is_latest选择使用哪个配置路径
            target_config_path = config_path if is_latest else config_old_path
            with open(target_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            # 获取并显示配置摘要信息
            outbounds = config.get('outbounds', [])
            print(f"[Singbox] 已获取 {'最新' if is_latest else '旧版'} 配置，{len(outbounds)} 个出站配置")

        else:
            print("[Singbox] 请求失败或内容为空")

    except Exception as e:
        print(f"[Singbox] 配置处理错误: {e}")
        print(f"[Singbox] 配置更新失败")
    

def replace_config(config: dict) -> dict:
    """修改配置中的路由规则"""

    # 获取并处理route配置（route是字典而不是列表）
    route = config.get('route', {})
    
    # 默认是直连
    route['final'] = "direct"

    # 添加Global规则集
    if 'rule_set' in route:
        route['rule_set'].append({
            "tag": "Global",
            "type": "remote",
            "format": "source",
            "url": "https://gh-proxy.org/https://raw.githubusercontent.com/ethanwwan/sing-box-rules/refs/heads/main/rule_json/Global_All.json",
            "download_detour": "direct"
        })

    # 添加Global规则
    if 'rules' in route:
        # 检查是否已存在相同的规则
        route['rules'].append({
            "rule_set": "Global",
            "outbound": "🚀 节点选择"
        })
                
    return config

def get_config_info():
    """获取当前配置信息"""

    config_data = None
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)


    except Exception as e:
        print(f"[Singbox] 获取配置信息错误: {e}")
    finally:
        return config_data



if __name__ == "__main__":
    # 测试功能
    print("=== Singbox 调度器测试 ===")
    
    # 显示当前配置信息
    print("\n--- 当前配置信息 ---")
    # print(get_config_info())
    
    # 执行配置更新
    print("\n--- 正在更新配置 ---")
    singbox_scheduler()
    
    print("\n=== 测试完成 ===")







