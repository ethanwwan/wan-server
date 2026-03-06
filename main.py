import threading
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
        run_now: 是否立即执行一次任务（异步执行，不阻塞）
    
    Returns:
        scheduler: 调度器实例
    """
    # 配置线程池执行器
    executors = {
        'default': APSchedulerThreadPoolExecutor(max_workers=10)
    }
    
    # 配置任务默认参数
    job_defaults = {
        'coalesce': False,              # 不合并错过的任务
        'max_instances': 1,             # 单个任务最多 1 个实例
        'misfire_grace_time': 300       # 任务错过执行时间后的宽容时间（5 分钟）
    }
    
    # 创建调度器
    scheduler = BackgroundScheduler(
        executors=executors, 
        job_defaults=job_defaults
    )
    
    # 注册定时任务
    for job_config in CONFIG.scheduler:
        func = job_config.get_func()
        if func:
            scheduler.add_job(
                func,
                trigger=CronTrigger(hour=job_config.hour, minute=job_config.minute),
                id=job_config.id,
                name=job_config.name,
                replace_existing=True
            )
    
    # 启动调度器
    scheduler.start()
    
    # 异步执行初始化任务（不阻塞主线程）
    if run_now:
        _run_init_tasks_async()
    
    return scheduler


def _run_init_tasks_async():
    """在后台线程中异步执行初始化任务
    
    Args:
        scheduler: 调度器实例
    """
    def run_jobs_async():
        for job_config in CONFIG.scheduler:
            func = job_config.get_func()
            if not func:
                continue
                
            try:
                func()
            except Exception as e:
                logger.error(f"❌ 任务失败 {job_config.name}: {e}", exc_info=True)
        
    # 启动守护线程执行初始化任务
    thread = threading.Thread(target=run_jobs_async, daemon=True, name="init-tasks")
    thread.start()
    logger.info("初始化任务已在后台启动（非阻塞）")

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
