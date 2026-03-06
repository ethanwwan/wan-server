import logging
import sys
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor as APSchedulerThreadPoolExecutor
from api.base.routes import api_router
from config.config import CONFIG
from utils.logger import get_logger
import atexit
import uvicorn


logger = get_logger('APP')

app = FastAPI(title="Wan API Server")
app.include_router(api_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


def setup_scheduler(run_now: bool = False):
    """根据配置初始化调度任务
    
    Args:
        run_now: 是否立即执行一次任务
    """
    executors = {
        'default': APSchedulerThreadPoolExecutor(max_workers=10)
    }
    job_defaults = {
        'coalesce': False,
        'max_instances': 1,
        'misfire_grace_time': 300
    }
    scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)
    
    for job in CONFIG.scheduler:
        func = job.get_func()
        if func:
            scheduler.add_job(
                func,
                trigger=CronTrigger(hour=job.hour, minute=job.minute),
                id=job.id,
                name=job.name,
                replace_existing=True
            )
            if run_now:
                func()
    
    scheduler.start()
    return scheduler

def start_server():

    logger.info("服务启动中...")
    logger.info(f"主机: {CONFIG.server.host}")
    logger.info(f"端口: {CONFIG.server.port}")
    logger.info(f"环境: {CONFIG.app.env}")
    logger.info(f"调试模式: {CONFIG.app.debug}")
    logger.info("服务启动完成")


    scheduler = setup_scheduler(run_now=False)
    def shutdown_handler():
        scheduler.shutdown()
        logger.info("服务已关闭")
    atexit.register(shutdown_handler)
    
    uvicorn.run(
        "main:app", 
        host=CONFIG.server.host,
        port=CONFIG.server.port,
        reload=False,
        log_level="warning"
    )


if __name__ == "__main__":
    start_server()
