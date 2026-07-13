import os
import json
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["TVBox"])

TVBOX_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'output', 'tvbox.json'
)


@router.get("/tvbox.json")
async def get_tvbox():
    if not os.path.exists(TVBOX_FILE):
        return {"code": 404, "msg": "tvbox.json 不存在", "data": None}
    return FileResponse(TVBOX_FILE, media_type="application/json")
