"""
TVBox配置管理API端点
提供TVBox配置文件的访问接口
"""

import os
import sys
import json
from fastapi import APIRouter, Request

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.base.response import not_found_response

router = APIRouter(prefix="/tvbox", tags=["TVBox"])

# TVBox配置目录
TVBOX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'public', 'tvbox')

def get_tvbox_local_file(file_name: str):
    """
    获取TVBox配置文件内容
    
    Args:
        file_name: 文件名
    
    Returns:
        dict: 配置文件内容
        None: 文件不存在或无法解析
    """
    file_path = os.path.join(TVBOX_DIR, file_name)
    
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content)
    except Exception:
        return None

# 自动扫描TVBox配置目录，获取所有JSON文件
def get_config_file_names():
    """
    扫描TVBox配置目录，获取所有JSON文件
    
    Returns:
        list: JSON文件列表
    """
    config_files = []
    if os.path.exists(TVBOX_DIR):
        for file_name in os.listdir(TVBOX_DIR):

            if file_name == "config.json":
                continue

            if file_name.endswith('.json'):
                config_files.append(file_name)
    return config_files

# 添加config.json路由
@router.get("/config.json")
async def get_tvbox_config_json(request: Request):
    """
    获取TVBox配置文件: config.json
    """
    data = get_tvbox_local_file("config.json")

    if data:
        print("获取到的config.json数据: " + json.dumps(data, ensure_ascii=False, indent=2))

        host = request.url.netloc

        # 将urls中的url中的localhost替换为当前请求的host
        urls = data.get('urls', [])
        for key in urls:
            key['url'] = key['url'].replace('localhost', host)

        return data
    else:
        return not_found_response(msg="配置文件 config.json 不存在或无法解析")

# 使用通配符路由处理所有TVBox配置文件请求
@router.get("/{file_name:path}")
async def get_tvbox_config_file(file_name: str):
    """获取TVBox配置文件"""
    # 检查文件是否存在
    file_path = os.path.join(TVBOX_DIR, file_name)
    
    if not os.path.exists(file_path):
        return not_found_response(msg=f"配置文件 {file_name} 不存在")
    
    # 读取并返回文件内容
    data = get_tvbox_local_file(file_name)
    
    if data:
        return data
    else:
        return not_found_response(msg=f"配置文件 {file_name} 无法解析")


if __name__ == "__main__":
    """
    测试TVBox配置管理API
    """
    print("开始测试TVBox配置管理API...")
    
    # 测试get_config_file_names函数
    print("\n1. 测试get_config_file_names函数:")
    config_files = get_config_file_names()
    print(f"获取到的配置文件列表: {config_files}")
    print(f"共找到 {len(config_files)} 个配置文件")
    
    # 测试其他文件
    if config_files:
        test_file = config_files[0]
        test_data = get_tvbox_local_file(test_file)
        if test_data:
            print(f"成功获取{test_file}文件内容")
            if 'sites' in test_data:
                print(f"{test_file}包含 {len(test_data['sites'])} 个站点")
        else:
            print(f"无法获取{test_file}文件内容")
    
    print("\n测试完成!")

