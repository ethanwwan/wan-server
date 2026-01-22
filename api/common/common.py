from fastapi import APIRouter, Request
from datetime import datetime
from api.base.response import success_response

router = APIRouter()

time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# API状态统计
@router.get("/stats")
async def api_stats(request: Request):
    """
    API统计信息
    
    返回API的统计信息和运行状态
    """
    return success_response(
        data={
            "total_endpoints": 3,
            "active_routes": [
                {"path": "/api/", "method": "GET", "description": "API信息"},
                {"path": "/api/stats", "method": "GET", "description": "API统计"},
                {"path": "/api/health", "method": "GET", "description": "健康检查"}
            ],
            "uptime": "running",
            "last_updated": time_now
        },
        msg="API statistics retrieved successfully",
        path=request.url.path,
        method=request.method
    )

@router.get("/health")
async def health_check(request: Request):
    """
    健康检查接口
    
    返回服务状态信息
    """
    # 使用标准响应格式
    return success_response(
        data=None,
        msg="Service is healthy"
    )

@router.get("/ping")
async def ping(request: Request):
    """
    Ping接口
    
    用于测试服务是否响应
    """
    return success_response(
        data={"pong": True, "timestamp": time_now},
        msg="Pong"
    )

@router.get("/status")
async def status(request: Request):
    """
    服务状态接口
    
    返回详细的服务状态信息
    """
    return success_response(
        data={
            "status": "healthy",
            "service": "api-server",
            "version": "1.0.0",
            "environment": "production",
            "timestamp": time_now,
            "features": {
                "scheduler": "enabled",
                "database": "connected",
                "cache": "available"
            }
        },
        msg="Service status retrieved successfully"
    )


@router.get("/time")
async def time_check():
    """时间接口"""
    return success_response(
        data={"timestamp": time_now},
        msg="Current time retrieved successfully"
    )