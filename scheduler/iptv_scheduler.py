"""
IPTV配置定时更新模块
负责每8小时自动更新IPTV配置文件
"""

import os
import requests
from datetime import datetime
import urllib3

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 写入本地配置文件，使用 UTF-8 编码，保存到项目根目录下的public/iptv目录
# 项目根目录是包含main.py的目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
iptv_dir = os.path.join(project_root, 'public', 'iptv')

# 从环境变量读取配置
PLAYLIST_URL = os.getenv("IPTV_PLAYLIST_URL", "http://192.168.1.12:8032/static/output/playlist.m3u")
MIGU_URL = os.getenv("IPTV_MIGU_URL", "http://192.168.1.12:8015/migu")
OTT_URL = os.getenv("IPTV_OTT_URL", "https://live.ottiptv.cc/iptv.m3u?userid=7755950497&sign=b7578005974939b989b3895b921110bcb06c83ed6f42b7139ba8b94c719484c980303585b7a1ffcc75c631fb0e9e8cd3983d6dc87447c558c9dc7770f76795671c177a0ad46048&auth_token=17b0d6712a2beb7e9bfea802dc9d33a3")

def iptv_scheduler():
    """
    每8小时更新一次IPTV配置
    
    功能：
    - 从三个不同的URL下载IPTV配置
    - 保存到本地public/iptv目录
    - 分别保存为 playlist.m3u, migu.m3u, ott.m3u
    """
    print(f"[IPTV] 开始更新配置，时间: {datetime.now().isoformat()}")
    
    # 确保public/iptv目录存在
    os.makedirs(iptv_dir, exist_ok=True)
    
    # 更新三个数据源
    update_playlist()
    update_migu()
    update_ott()
    
    print(f"[IPTV] 配置更新成功完成，时间: {datetime.now().isoformat()}")

def update_playlist():
    """更新NAS播放列表"""
    if not PLAYLIST_URL:
        print("[IPTV] NAS播放列表URL未配置，跳过")
        return
    
    try:
        print(f"[IPTV] 正在获取NAS播放列表...")
        response = requests.get(PLAYLIST_URL, verify=False, timeout=20)
        
        if response.status_code == 200 and response.text.strip():
            file_path = os.path.join(iptv_dir, 'playlist.m3u')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response.text.strip())
            print(f"[IPTV] NAS播放列表已保存到 {file_path}")
        else:
            print("[IPTV] NAS播放列表请求失败或内容为空")
    except Exception as e:
        print(f"[IPTV] 更新NAS播放列表失败: {e}")

def update_migu():
    """更新Migu播放列表"""
    if not MIGU_URL:
        print("[IPTV] Migu播放列表URL未配置，跳过")
        return
    
    try:
        print(f"[IPTV] 正在获取Migu播放列表...")
        response = requests.get(MIGU_URL, verify=False, timeout=20)
        
        if response.status_code == 200 and response.text.strip():
            file_path = os.path.join(iptv_dir, 'migu.m3u')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response.text.strip())
            print(f"[IPTV] Migu播放列表已保存到 {file_path}")
        else:
            print("[IPTV] Migu播放列表请求失败或内容为空")
    except Exception as e:
        print(f"[IPTV] 更新Migu播放列表失败: {e}")

def update_ott():
    """更新OTT播放列表"""
    if not OTT_URL:
        print("[IPTV] OTT播放列表URL未配置，跳过")
        return
    
    try:
        print(f"[IPTV] 正在获取OTT播放列表...")
        response = requests.get(OTT_URL, verify=False, timeout=20)
        
        if response.status_code == 200 and response.text.strip():
            file_path = os.path.join(iptv_dir, 'ott.m3u')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response.text.strip())
            print(f"[IPTV] OTT播放列表已保存到 {file_path}")
        else:
            print("[IPTV] OTT播放列表请求失败或内容为空")
    except Exception as e:
        print(f"[IPTV] 更新OTT播放列表失败: {e}")

def get_iptv_file_content(file_name: str) -> str:
    """
    获取IPTV文件内容
    
    Args:
        file_name: 文件名（如 playlist.m3u, migu.m3u, ott.m3u）
    
    Returns:
        str: 文件内容，如果文件不存在则返回空字符串
    """
    file_path = os.path.join(iptv_dir, file_name)
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return ""
    except Exception as e:
        print(f"[IPTV] 读取文件失败: {file_name}, 错误: {e}")
        return ""

if __name__ == "__main__":
    # 测试功能
    print("=== IPTV 调度器测试 ===")
    
    # 执行配置更新
    print("\n--- 正在更新配置 ---")
    iptv_scheduler()
    
    print("\n=== 测试完成 ===")
