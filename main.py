"""

source .venv/bin/activate

deactivate

"""

from fastapi import FastAPI,Request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.singbox_scheduler import singbox_scheduler
from api.routes import api_router
from api.singbox_api import router as singbox_router
from api.iptv_api import router as iptv_router
from api.response import success_response
import atexit

app = FastAPI(title="Lightweight API Backend")

# 挂载API路由
app.include_router(api_router)
app.include_router(singbox_router)
app.include_router(iptv_router)

# root路由
@app.get("/")
async def root(request: Request):
    return success_response(
        data=None,
        msg="Service is running."
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


# 在服务启动时立即执行一次配置更新
singbox_scheduler()

# Optional: Shutdown scheduler gracefully on app exit (for production)
atexit.register(lambda: scheduler.shutdown())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)