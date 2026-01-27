"""
TVBox配置管理API端点
提供TVBox配置文件的访问接口
"""

import os
import sys
import json
from fastapi import APIRouter, Request, Response
from api.base.response import not_found_response

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

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


