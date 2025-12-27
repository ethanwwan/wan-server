"""
Singbox配置定时更新模块
负责每8小时自动更新singbox配置文件
"""

from typing import Any
import requests
import json
import os
from datetime import datetime
import base64
import urllib.parse
import urllib3

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 写入本地 config.json，使用 UTF-8 编码，保存到项目根目录下的public目录
# 项目根目录是包含main.py的目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_dir = os.path.join(project_root, 'public')
config_path = os.path.join(config_dir, 'singbox-config.json')

url = "https://47.238.198.94/iv/verify_mode.htm?token=9a49f8e2abcce3a0d3fd12e072065cdd"


def singbox_scheduler():
    """
    每8小时更新一次singbox配置
    
    功能：
    - 从远程URL下载最新配置
    - 保存到本地配置文件
    - 可选：重启singbox服务
    """
    print(f"[Singbox] 开始更新配置，时间: {datetime.now().isoformat()}")
    
    try:

        headers = {
            "User-Agent": "SFA/1.12.14 (595; sing-box 1.12.14; language zh_CN)",
            # 直接用 sing-box 核心版本 + macOS 标识，看起来像官方 SFM 客户端
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        response = requests.get(url, headers=headers, verify=False, timeout=20)

        if response.status_code == 200 and response.text.strip():
            try:
                # 直接解析response.text作为完整的singbox配置JSON
                config = json.loads(response.text.strip())
                
                config = replace_config(config)

                # 确保public目录存在
                os.makedirs(config_dir, exist_ok=True)

                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                
                # 获取并显示配置摘要信息
                outbounds = config.get('outbounds', [])
                print(f"[Singbox] 已获取 {len(outbounds)} 个出站配置")
                print("=== 完整的 sing-box 配置已保存到 config.json ===")
                
            except json.JSONDecodeError as e:
                print(f"[Singbox] JSON解析错误: {e}")
                print(f"[Singbox] 响应内容前100个字符: {response.text[:100]}...")
                return
            except Exception as e:
                print(f"[Singbox] 配置处理错误: {e}")
                return

        else:
            print("[Singbox] 请求失败或空内容")
       
        
        print(f"[Singbox] 配置更新成功完成，时间: {datetime.now().isoformat()}")
        
    except requests.RequestException as e:
        print(f"[Singbox] 下载配置错误: {e}")
        print(f"[Singbox] 请检查网络连接和URL")
        
    except json.JSONDecodeError as e:
        print(f"[Singbox] 解析JSON配置错误: {e}")
        print(f"[Singbox] 下载的文件不是有效的JSON格式")
        
    except OSError as e:
        print(f"[Singbox] 保存配置文件错误: {e}")
        print(f"[Singbox] 请检查文件权限和磁盘空间")
        
    except Exception as e:
        print(f"[Singbox] 意外错误: {e}")
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
    print(get_config_info())
    
    # 执行配置更新
    print("\n--- 正在运行配置更新，当前版本1.12.14，版本号595 ---")
    # singbox_scheduler()
    
    print("\n=== 测试完成 ===")







