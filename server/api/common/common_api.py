"""
Common API - 健康检查、状态、统计等通用端点
"""
from datetime import datetime
from fastapi import APIRouter
from fastapi.routing import APIRoute

from ..base.response import success_response

router = APIRouter(prefix="/common", tags=["Common"])


def _now() -> str:
    """当前时间（每次调用都重新获取）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _list_routes() -> list:
    """
    动态收集所有已注册的路由（自动维护，不会过期）

    启动时由主应用通过 set_app() 注入
    """
    app = _get_app()
    if not app:
        return []
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            for method in (route.methods or []):
                if method in ("GET", "POST", "PUT", "DELETE"):
                    routes.append({
                        "path": route.path,
                        "method": method,
                        "description": route.name or "",
                    })
    return routes


# 简易的 app 引用注入（启动时由 main 设置）
_app_ref = None


def _get_app():
    return _app_ref


def set_app(app):
    """主应用启动时调用，注入 FastAPI 实例用于动态路由枚举"""
    global _app_ref
    _app_ref = app


@router.get("/stats")
async def api_stats():
    """API 统计信息"""
    routes = _list_routes()
    return success_response(
        data={
            "total_endpoints": len(routes),
            "active_routes": routes,
            "uptime": "running",
            "last_updated": _now(),
        },
        msg="API 统计信息获取成功"
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return success_response(
        data=None,
        msg="服务运行正常"
    )


@router.get("/ping")
async def ping():
    """Ping 测试"""
    return success_response(
        data={"pong": True, "timestamp": _now()},
        msg="响应成功"
    )


@router.get("/status")
async def status():
    """服务状态（仅报告已确认的项）"""
    return success_response(
        data={
            "status": "healthy",
            "service": "wan-server",
            "version": "2.5.5",
            "environment": "production",
            "timestamp": _now(),
            "features": {
                "scheduler": "enabled",
            },
        },
        msg="服务状态获取成功"
    )


@router.get("/time")
async def time_check():
    """当前时间（每次调用都获取新值）"""
    return success_response(
        data={"timestamp": _now()},
        msg="当前时间获取成功"
    )