from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.singbox_scheduler import singbox_scheduler
from scheduler.tvbox_scheduler import tvbox_scheduler
from scheduler.iptv_scheduler import iptv_scheduler
from api.base.routes import api_router
from api.base.response import success_response
from dotenv import load_dotenv
import os
import atexit
import uvicorn

load_dotenv()
app = FastAPI(title="Lightweight API Backend")
app.include_router(api_router)

@app.get("/")
async def root():
    return success_response(
        data=None,
        msg="服务正在运行中。"
    )


scheduler = BackgroundScheduler()
scheduler.start()

scheduler.add_job(
    singbox_scheduler,
    trigger=IntervalTrigger(hours=8),
    id="singbox_job",
    name="Singbox configuration update",
    replace_existing=True
)

# 添加TVBox配置更新任务
scheduler.add_job(
    tvbox_scheduler,
    trigger=IntervalTrigger(hours=8),
    id="tvbox_job",
    name="TVBox configuration update",
    replace_existing=True
)

# 添加IPTV配置更新任务
scheduler.add_job(
    iptv_scheduler,
    trigger=IntervalTrigger(hours=8),
    id="iptv_job",
    name="IPTV configuration update",
    replace_existing=True
)

atexit.register(lambda: scheduler.shutdown())

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0",
        port=8016,
        reload=os.getenv("APP_ENV") == "dev"
    )