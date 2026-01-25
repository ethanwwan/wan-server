"""

source .venv/bin/activate

deactivate

"""

from fastapi import FastAPI,Request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.singbox_scheduler import singbox_scheduler
from scheduler.tvbox_scheduler import tvbox_scheduler
from api.base.routes import api_router

from api.base.response import success_response
import atexit

app = FastAPI(title="Lightweight API Backend")
app.include_router(api_router)

# root路由
@app.get("/")
async def root(request: Request):
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


# 在服务启动时立即执行一次配置更新
# singbox_scheduler()
# tvbox_scheduler()

# Optional: Shutdown scheduler gracefully on app exit (for production)
atexit.register(lambda: scheduler.shutdown())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)