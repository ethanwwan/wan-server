from fastapi import APIRouter, Request
from datetime import datetime
from api.response import success_response

router = APIRouter()

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
            "last_updated": datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        },
        message="API statistics retrieved successfully",
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
        data={ },
        message="Service is healthy"
    )

@router.get("/ping")
async def ping(request: Request):
    """
    Ping接口
    
    用于测试服务是否响应
    """
    return success_response(
        data={"pong": True, "timestamp": datetime.now().strftime("%Y-%m-%d %H%M%S")},
        message="Pong"
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
            "timestamp": datetime.now().strftime("%Y-%m-%d %H%M%S"),
            "features": {
                "scheduler": "enabled",
                "database": "connected",
                "cache": "available"
            }
        },
        message="Service status retrieved successfully"
    )


@router.get("/time")
async def time_check():
    """时间接口"""
    return success_response(
        data={"timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S")},
        message="Current time retrieved successfully"
    )