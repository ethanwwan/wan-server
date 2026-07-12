#!/usr/bin/env python3
"""
日志配置模块
"""

import logging
import sys
import os
import urllib3
# from config import CONFIG

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def configure_logging():
    """配置日志系统"""

    # log_level = logging.DEBUG if CONFIG.app.debug else logging.INFO
    log_level = logging.INFO

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # 设置日志格式
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # 添加控制台处理器
    root_logger.addHandler(console_handler)
    
    # 为第三方库设置 WARNING 级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    
    # 屏蔽 uvicorn 日志
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(logging.NullHandler())


# 模块加载时自动配置日志
configure_logging()


# 便捷函数
def get_logger(name: str = 'APP') -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)
