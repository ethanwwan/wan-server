"""
Singbox配置定时更新模块
负责每8小时自动更新singbox配置文件
"""

from pickle import NONE
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
    print(f"[Singbox] Starting configuration update at {datetime.now().isoformat()}")
    
    try:

        headers = {
            "User-Agent": "SFA (Macintosh; Intel Mac OS X 10_15_7)",
            # 直接用 sing-box 核心版本 + macOS 标识，看起来像官方 SFM 客户端
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        response = requests.get(url, headers=headers, verify=False, timeout=20)

        if response.status_code == 200 and response.text.strip():
            # Base64 解码
            decoded = base64.b64decode(response.text.strip()).decode('utf-8')
            
            # 分行处理链接
            lines = [line.strip() for line in decoded.split('\n') if line.strip()]

            outbounds = []

            for line in lines:
                # 替换 &amp; 为 & 以正确解析 query
                line = line.replace('&amp;', '&')
                
                # 处理 URL 中的 # 号之前的部分和备注
                if '#' in line:
                    url_part, remark_encoded = line.split('#', 1)
                    remark = urllib.parse.unquote(remark_encoded)  # 解码 %XX 为中文/Emoji
                else:
                    continue

                # 解析 URL
                parsed = urllib.parse.urlparse(url_part)

                if parsed.scheme == 'hysteria2':
                    # Hysteria2 解析
                    netloc_parts = parsed.netloc.split('@')
                    password = netloc_parts[0] if len(netloc_parts) > 1 else ''
                    server_port = netloc_parts[1] if len(netloc_parts) > 1 else parsed.netloc
                    server, port = server_port.rsplit(':', 1) if ':' in server_port else (server_port, '16883')
                    params = urllib.parse.parse_qs(parsed.query)
                    sni = params.get('sni', [''])[0]
                    insecure = bool(int(params.get('insecure', ['0'])[0]))
                    
                    outbound = {
                        "type": "hysteria2",
                        "tag": remark,
                        "server": server,
                        "server_port": int(port),
                        "password": password,
                        "tls": {
                            "enabled": True,
                            "server_name": sni,
                            "insecure": insecure
                        }
                    }
                    outbounds.append(outbound)
                
                elif parsed.scheme == 'vless':
                    # VLESS 解析
                    netloc_parts = parsed.netloc.split('@')
                    uuid = netloc_parts[0] if len(netloc_parts) > 1 else ''
                    server_port = netloc_parts[1] if len(netloc_parts) > 1 else parsed.netloc
                    server, port = server_port.rsplit(':', 1) if ':' in server_port else (server_port, '443')
                    params = urllib.parse.parse_qs(parsed.query)
                    mode = params.get('mode', [''])[0]
                    security = params.get('security', ['none'])[0]
                    encryption = params.get('encryption', ['none'])[0]
                    type_ = params.get('type', [''])[0]
                    sni = params.get('sni', [''])[0]
                    fp = params.get('fp', [''])[0]
                    path = urllib.parse.unquote(params.get('path', [''])[0])  # 解码 path
                    host = params.get('host', [''])[0]
                    
                    outbound = {
                        "type": "vless",
                        "tag": remark,
                        "server": server,
                        "server_port": int(port),
                        "uuid": uuid,
                        "packet_encoding": "xudp" if encryption == 'none' else "",
                        "tls": {
                            "enabled": security == 'tls',
                            "server_name": sni,
                            "insecure": False,
                            "utls": {
                                "enabled": bool(fp),
                                "fingerprint": fp
                            }
                        },
                        "transport": {
                            "type": type_,
                            "path": path,
                            "headers": {
                                "Host": host
                            }
                        } if type_ else {}
                    }
                    outbounds.append(outbound)

            # 添加自动选优组（urltest）作为默认出站
            auto_outbound = {
                "type": "urltest",
                "tag": "♻️ 自动选择",
                "outbounds": [out["tag"] for out in outbounds],
                "url": "http://www.apple.com/library/test/success.html",
                "interval": "30m",
                "idle_timeout": "30m",
                "tolerance": 50
            }
            
            outbounds.insert(0, auto_outbound)
            
            selector_outbound = {
                "type": "selector",
                "tag": "🚀 节点选择",
                "outbounds": [out["tag"] for out in outbounds]
            }
            
            outbounds.insert(0, selector_outbound)
            
            outbounds.append({
                "type": "direct",
                "tag": "direct"
            })

            # 生成完整的 sing-box 配置
            config = generate_json(outbounds)
            
            # 确保public目录存在
            os.makedirs(config_dir, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            
            print("=== 完整的 Sing-box 配置已生成并写入 config.json ===")

        else:
            print("请求失败或空内容")
       
        
        print(f"[Singbox] Configuration update completed successfully at {datetime.now().isoformat()}")
        
    except requests.RequestException as e:
        print(f"[Singbox] Error downloading configuration: {e}")
        print(f"[Singbox] Please check your network connection and URL")
        
    except json.JSONDecodeError as e:
        print(f"[Singbox] Error parsing JSON configuration: {e}")
        print(f"[Singbox] The downloaded file is not valid JSON format")
        
    except OSError as e:
        print(f"[Singbox] Error saving configuration file: {e}")
        print(f"[Singbox] Please check file permissions and disk space")
        
    except Exception as e:
        print(f"[Singbox] Unexpected error: {e}")
        print(f"[Singbox] Configuration update failed")


def get_config_info():
    """获取当前配置信息"""
  
    config_data = None

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            if config_data:
                # 将config_data转换为JSON字符串，然后进行base64编码
                config_str = json.dumps(config_data, ensure_ascii=False, indent=4)
                config_bytes = config_str.encode('utf-8')
                config_data = base64.b64encode(config_bytes).decode('utf-8')

    except Exception as e:
        print(f"[Singbox] Error getting config info: {e}")
    finally:
        return config_data


def generate_json(outbounds:Any):
    return {
                "log": {
                    "disabled": False,
                    "level": "info",
                    "timestamp": True
                },
                "experimental": {
                    "clash_api": {
                        "external_controller": "127.0.0.1:9090",
                        "external_ui": "metacubexd",
                        "external_ui_download_url": "https://github.com/MetaCubeX/metacubexd/archive/refs/heads/gh-pages.zip",
                        "external_ui_download_detour": "🚀 节点选择",
                        "secret": "",
                        "default_mode": "智能分流",
                        "access_control_allow_origin": "*",
                        "access_control_allow_private_network": False
                    },
                    "cache_file": {
                        "enabled": True,
                        "store_rdrc": True
                    }
                },
                "dns": {
                    "servers": [
                        {
                            "tag": "dns_proxy",
                            "address": "https://1.1.1.1/dns-query",
                            "detour": "🚀 节点选择"
                        },
                        {
                            "tag": "dns_local",
                            "address": "https://223.5.5.5/dns-query",
                            "detour": "direct"
                        }
                    ],
                    "rules": [
                        {
                            "clash_mode": "全球直连",
                            "server": "dns_local"
                        },
                        {
                            "clash_mode": "全局代理",
                            "server": "dns_proxy"
                        },
                        {
                            "rule_set": [
                                "geosite-cn",
                                "geoip-cn"
                            ],
                            "server": "dns_local"
                        }
                    ],
                    "strategy": "prefer_ipv4",
                    "final": "dns_local"
                },
                "inbounds": [
                    {
                        "type": "tun",
                        "tag": "tun-in",
                        "stack": "mixed",
                        "mtu": 9000,
                        "address": [
                            "172.19.0.1/30",
                            "2001:0470:f9da:fdfa::1/64"
                        ],
                        "auto_route": True,
                        "strict_route": True,
                        "sniff": True,
                        "sniff_override_destination": True
                    }
                ],
                "outbounds": outbounds,
                "route": {
                    "final": "direct",
                    "auto_detect_interface": True,
                    "rules": [
                        {
                            "type": "logical",
                            "mode": "or",
                            "rules": [
                                {
                                    "protocol": "dns"
                                },
                                {
                                    "port": 53
                                }
                            ],
                            "action": "hijack-dns"
                        },
                        {
                            "clash_mode": "全球直连",
                            "outbound": "direct"
                        },
                        {
                            "clash_mode": "全局代理",
                            "outbound": "🚀 节点选择"
                        },
                        {
                            "ip_is_private": True,
                            "outbound": "direct"
                        },
                        {
                            "rule_set": [
                                "geosite-cn",
                                "geoip-cn"
                            ],
                            "outbound": "direct"
                        },
                        {
                            "rule_set": "Global",
                            "outbound": "🚀 节点选择"
                        }
                    ],
                    "rule_set": [
                        {
                            "type": "remote",
                            "tag": "geoip-cn",
                            "format": "binary",
                            "url": "https://gh-proxy.org/https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-cn.srs",
                            "download_detour": "direct"
                        },
                        {
                            "type": "remote",
                            "tag": "geosite-cn",
                            "format": "binary",
                            "url": "https://gh-proxy.org/https://raw.githubusercontent.com/SagerNet/sing-geosite/refs/heads/rule-set/geosite-cn.srs",
                            "download_detour": "direct"
                        },
                        {
                            "tag": "Global",
                            "type": "remote",
                            "format": "source",
                            "url": "https://gh-proxy.org/https://raw.githubusercontent.com/ethanwwan/sing-box-rules/refs/heads/main/rule_json/Global_All.json",
                            "download_detour": "direct"
                        }
                    ]
                }
            }


if __name__ == "__main__":
    # 测试功能
    print("=== Singbox Scheduler Test ===")
    
    # 显示当前配置信息
    print("\n--- Current Configuration Info ---")
    print(get_config_info())
    
    # 执行配置更新
    print("\n--- Running Configuration Update ---")
    # singbox_scheduler()
    
    print("\n=== Test Completed ===")







