#!/usr/bin/env python3
"""
转换 fail_cache.json 格式
从复杂格式转为简化格式
"""

import json
import os

def convert_cache_format():
    cache_path = '/Users/Awan/Public/Repository/wan-server/output/iptv/cache/fail_cache.json'
    
    # 检查文件是否存在
    if not os.path.exists(cache_path):
        print(f"文件不存在: {cache_path}")
        return
    
    # 读取旧格式
    with open(cache_path, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    
    # 转换为新格式
    new_data = {url: 1 for url in old_data.keys()}
    
    # 统计
    old_count = len(old_data)
    new_count = len(new_data)
    
    print(f"旧格式条目数: {old_count}")
    print(f"新格式条目数: {new_count}")
    
    # 写入新格式
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    
    print(f"转换完成！")
    print(f"文件已更新: {cache_path}")

if __name__ == '__main__':
    convert_cache_format()
