#!/usr/bin/env python3
"""
IPTV 频道检测测试工具
用于测试 migu.m3u 文件中的频道，调整 ffmpeg 参数
"""

import os
import re
import subprocess
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.config import CONFIG
from utils.logger import get_logger

IPTV_DIR = os.path.join(project_root, 'public', 'iptv')

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
FPS_MIN = 24

logger = get_logger('IPTV')


def parse_m3u(content: str) -> list:
    if not content:
        return []

    channels = []
    lines = content.split('\n')
    print(f"[parse_m3u] 总行数：{len(lines)}")
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # print(f"[parse_m3u] 第 {i} 行：'{line[:100]}...'")
        
        if line.startswith('#EXTINF:'):
            # print(f"[parse_m3u] 找到 #EXTINF 行：i={i}")
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url and not url.startswith('#'):
                    ext_info = line
                    tvg_id = re.search(r'tvg-id="([^"]*)"', ext_info)
                    tvg_name = re.search(r'tvg-name="([^"]*)"', ext_info)
                    tvg_logo = re.search(r'tvg-logo="([^"]*)"', ext_info)
                    group = re.search(r'group-title="([^"]*)"', ext_info)
                    comma = re.search(r',(.+)$', ext_info)

                    ch = {
                        'tvg_id': tvg_id.group(1).strip() if tvg_id else "",
                        'tvg_name': tvg_name.group(1).strip() if tvg_name else "",
                        'tvg_logo': tvg_logo.group(1).strip() if tvg_logo else "",
                        'group_title': group.group(1).strip() if group else "",
                        'channel_name': (comma.group(1).strip() if comma else "") or (tvg_name.group(1).strip() if tvg_name else ""),
                        'url': url
                    }
                    if ch['url'] and ch['channel_name']:
                        channels.append(ch)
        i += 1
    print(f"[parse_m3u] 找到 {len(channels)} 个频道")
    return channels


def check_url_available(url: str, timeout: int = 5) -> bool:
    print(f"  [基础检测] timeout={timeout}s")
    
    cmd = [
        'ffmpeg',
        '-i', url,
        '-t', '2',
        '-f', 'null', '-',
        '-v', 'error',
        '-hide_banner'
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            print(f"  [超时] {url[:50]}...")
            return False
        
        print(f"  [调试] returncode={process.returncode}, stderr={len(stderr)} chars")
        
        error_log = stderr.lower()

        unavailable_keywords = [
            '404', 'not found', 'file not found',
            'connection refused',
            'connection timeout', 'connection timed out',
            'unable to open', 'server returned 403 forbidden',
            'invalid data found when processing input'
        ]

        if any(keyword in error_log for keyword in unavailable_keywords):
            print(f"  [失败] 命中错误关键词：{error_log[:100]}")
            return False

        if process.returncode != 0 and not any(keyword in error_log for keyword in unavailable_keywords):
            print(f"  [通过] returncode={process.returncode}")
            return True

        print(f"  [通过] returncode={process.returncode}")
        return True

    except Exception as e:
        print(f"  [异常] {e}")
        return False


def check_url_fluent(url: str, timeout: int = 15) -> bool:
    print(f"  [流畅检测] timeout={timeout}s")
    
    # 多种 ffmpeg 参数组合，逐步尝试
    cmd_configs = [
        # 方案 1: 简单探测（最常用）
        [
            'ffmpeg',
            '-i', url,
            '-t', '3',
            '-v', 'info',
            '-f', 'null', '-'
        ],
        # 方案 2: 更详细的输出
        [
            'ffmpeg',
            '-i', url,
            '-t', '5',
            '-v', 'verbose',
            '-f', 'null', '-'
        ],
        # 方案 3: 最短超时
        [
            'ffmpeg',
            '-i', url,
            '-t', '2',
            '-v', 'warning',
            '-f', 'null', '-'
        ]
    ]
    
    for attempt, cmd in enumerate(cmd_configs, 1):
        print(f"  [尝试 {attempt}/{len(cmd_configs)}] 方案：{cmd[3]}")
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                print(f"  [超时] {url[:50]}...")
                continue
            
            print(f"  [调试] returncode={process.returncode}, stderr={len(stderr)} chars")
            
            # 检查是否有正常播放的信息
            error_log = stderr.lower()
            
            # 检查是否有帧输出（表示视频在播放）
            if 'frame=' in error_log and 'fps=' in error_log:
                # 提取帧率和 FPS 信息
                import re
                # 尝试匹配最后的 fps 值（通常在日志末尾）
                fps_matches = re.findall(r'fps=(\d+\.?\d*)', error_log)
                if fps_matches:
                    # 取最后一个 fps 值（最新的）
                    fps = float(fps_matches[-1])
                    print(f"  [视频] fps={fps:.2f}, min={FPS_MIN}")
                    if fps > 0 and fps < FPS_MIN:
                        print(f"  [失败] 帧率低于阈值")
                        return False
                else:
                    print(f"  [视频] 无法提取 fps")
                
                print(f"  [通过] 检测到正常播放帧")
                return True
            
            # 检查是否有严重错误
            unavailable_keywords = [
                '404', 'not found', 'file not found',
                'connection refused',
                'connection timeout', 'connection timed out',
                'unable to open', 'server returned 403',
                'invalid data', 'option not found'
            ]
            
            if any(keyword in error_log for keyword in unavailable_keywords):
                print(f"  [失败] 命中错误关键词")
                return False
            
            # 如果 returncode 为 0，也认为成功
            if process.returncode == 0:
                print(f"  [通过] returncode=0")
                return True
            
            print(f"  [重试] 未获取到有效信息，尝试下一个方案")
            
        except Exception as e:
            print(f"  [异常] 方案{attempt}失败：{e}")
            continue
    
    # 所有方案都失败了
    print(f"  [失败] 所有方案都无法获取流信息")
    return False


def check_channel(ch: dict) -> dict:
    url = ch.get('url', '')
    if not url:
        return None
    
    channel_name = ch.get('channel_name', 'Unknown')
    print(f"\n频道：{channel_name}")
    print(f"URL: {url}")
    
    if not check_url_available(url, 10):
        print(f"结果：✗ 基础可用性检测失败")
        return None
    
    if not check_url_fluent(url, 15):
        print(f"结果：✗ 流畅度检测失败")
        return None
    
    print(f"结果：✓ 通过")
    return ch


def get_iptv_content(filename: str) -> str:
    path = os.path.join(IPTV_DIR, filename)
    try:
        return open(path, 'r', encoding='utf-8').read() if os.path.exists(path) else ""
    except Exception as e:
        print(f"读取文件失败：{filename}, 错误：{e}")
        return ""


if __name__ == "__main__":
    print(f"项目根目录：{project_root}")
    print(f"IPTV 目录：{IPTV_DIR}")
    print(f"IPTV 目录存在：{os.path.exists(IPTV_DIR)}")
    
    migu_file = os.path.join(IPTV_DIR, 'migu.m3u')
    print(f"migu.m3u 路径：{migu_file}")
    print(f"migu.m3u 存在：{os.path.exists(migu_file)}")
    
    if not os.path.exists(migu_file):
        print(f"文件不存在：{migu_file}")
        print("请先运行 fetch_migu() 获取 migu 播放列表")
        exit(1)
    
    content = get_iptv_content('migu.m3u')
    channels = parse_m3u(content)
    
    print(f"=== IPTV 频道测试工具 ===")
    print(f"共 {len(channels)} 个频道\n")
    
    for i, ch in enumerate(channels[:20]):
        print(f"{i + 1}. {ch['channel_name']}")
    
    print("\n请输入要测试的频道编号 (输入 q 退出): ")
    
    while True:
        choice = input("> ").strip()
        if choice.lower() == 'q':
            break
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(channels):
                ch = channels[idx]
                check_channel(ch)
            else:
                print(f"编号范围：1-{len(channels)}")
        except ValueError:
            print("请输入有效编号")
    
    print("\n测试结束")
