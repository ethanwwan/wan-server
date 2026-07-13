import importlib
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from logger import get_logger
import uvicorn

routes_module = importlib.import_module("nas-server.api.base.routes")
api_router = routes_module.api_router

scheduler = importlib.import_module("nas-server.schedulers.tvbox_scheduler")

logger = get_logger('APP')

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8016


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动，执行 NAS 调度任务...")
    scheduler.run()
    yield


app = FastAPI(title="Wan API Server", lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok"}


def start_server():
    logger.info("服务启动中...")
    logger.info(f"主机: {SERVER_HOST}")
    logger.info(f"端口: {SERVER_PORT}")
    logger.info("服务启动完成")

    uvicorn.run(
        "main:app", 
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="warning"
    )


if __name__ == "__main__":
    start_server()