"""
统一API响应格式模块
提供标准化的响应数据结构
"""

from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """
    标准API响应格式
    
    所有API响应都应该使用这个格式，确保一致性
    """
    code: int = Field(..., description="状态码")
    msg: str = Field(..., description="响应消息")
    data: Optional[Any] = Field(None, description="响应数据")
   
    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
                "msg": "Success",
                "data": {"key": "value"}
            }
        }


class ResponseCodes:
    """
    标准状态码定义
    """
    # 成功状态码
    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    
    # 客户端错误
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    
    # 服务器错误
    INTERNAL_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


class ResponseMessages:
    """
    标准消息定义
    """
    # 成功消息
    SUCCESS = "操作成功"
    CREATED = "创建成功"
    UPDATED = "更新成功"
    DELETED = "删除成功"
    
    # 错误消息
    BAD_REQUEST = "请求参数错误"
    UNAUTHORIZED = "未授权访问"
    FORBIDDEN = "权限不足"
    NOT_FOUND = "资源不存在"
    INTERNAL_ERROR = "服务器内部错误"
    SERVICE_UNAVAILABLE = "服务暂不可用"


def success_response(
    data: Any = None,
    msg: str = ResponseMessages.SUCCESS,
    code: int = ResponseCodes.SUCCESS
) -> ApiResponse:
    """
    创建成功响应
    
    Args:
        data: 响应数据
        msg: 响应消息
        code: 状态码
    
    Returns:
        ApiResponse: 标准响应对象
    """
    return ApiResponse(
        code=code,
        msg=msg,
        data=data
    )


def error_response(
    msg: str = ResponseMessages.INTERNAL_ERROR,
    code: int = ResponseCodes.INTERNAL_ERROR,
    data: Optional[Any] = None
) -> ApiResponse:
    """
    创建错误响应
    
    Args:
        msg: 错误消息
        code: 错误状态码
        data: 额外的错误数据
    
    Returns:
        ApiResponse: 标准响应对象
    """
    return ApiResponse(
        code=code,
        msg=msg,
        data=data
    )


def not_found_response(
    msg: str = ResponseMessages.NOT_FOUND,
    data: Optional[Any] = None
) -> ApiResponse:
    """
    创建资源不存在响应
    """
    return error_response(
        msg=msg,
        code=ResponseCodes.NOT_FOUND,
        data=data
    )


def unauthorized_response(
    msg: str = ResponseMessages.UNAUTHORIZED,
    data: Optional[Any] = None
) -> ApiResponse:
    """
    创建未授权响应
    """
    return error_response(
        msg=msg,
        code=ResponseCodes.UNAUTHORIZED,
        data=data
    )


def bad_request_response(
    msg: str = ResponseMessages.BAD_REQUEST,
    data: Optional[Any] = None
) -> ApiResponse:
    """
    创建请求参数错误响应
    """
    return error_response(
        msg=msg,
        code=ResponseCodes.BAD_REQUEST,
        data=data
    )


def paginated_response(
    items: list,
    total: int,
    page: int,
    size: int,
    msg: str = ResponseMessages.SUCCESS
) -> ApiResponse:
    """
    创建分页响应
    
    Args:
        items: 当前页数据列表
        total: 总记录数
        page: 当前页码
        size: 每页大小
        msg: 响应消息
        path: 请求路径
        method: 请求方法
    
    Returns:
        ApiResponse: 包含分页信息的标准响应
    """
    total_pages = (total + size - 1) // size  # 向上取整
    
    pagination_data = {
        "items": items,
        "pagination": {
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
    
    return success_response(
        data=pagination_data,
        msg=msg
    )


# 常用响应模板
RESPONSE_TEMPLATES = {
    "health_check": lambda: success_response(
        data={"status": "healthy", "service": "api-server"},
        msg="Service is healthy"
    ),
    "ping": lambda: success_response(
        data={"pong": True},
        msg="Pong"
    ),
    "version": lambda version: success_response(
        data={"version": version},
        msg="Version information"
    )
}