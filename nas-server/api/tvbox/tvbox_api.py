import os
import json
from fastapi import APIRouter

router = APIRouter(prefix="/tvbox", tags=["TVBox"])

TVBOX_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    'nas-server', 'output', 'tvbox.json'
)


@router.get("")
async def get_tvbox():
    if not os.path.exists(TVBOX_FILE):
        return {"code": 404, "msg": "tvbox.json 不存在", "data": None}
    try:
        with open(TVBOX_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"code": 500, "msg": f"读取失败: {e}", "data": None}
