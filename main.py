from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from api.base.routes import api_router
from utils.logger import get_logger
import uvicorn

logger = get_logger('APP')

# 硬编码配置
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8016

app = FastAPI(title="Wan API Server")
app.include_router(api_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


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