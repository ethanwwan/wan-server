"""
Scheduler 通用基类

提供所有 scheduler 共享的能力：
  - 项目根目录获取
  - 统一配置加载
  - 统一 logger
  - 通用 run() 调度循环

使用方式：
    from server.utils.scheduler_base import SchedulerBase

    class IptvScheduler(SchedulerBase):
        name = 'NAS_IPTV'

        def sync(self) -> bool:
            # 业务逻辑
            ...
"""
import os
import sys
import time
import schedule
from typing import Optional

from logger import get_logger
from .constants import load_config


class SchedulerBase:
    """
    Scheduler 基类

    子类需要：
      - 定义类变量 name（logger 名字）
      - 实现 sync() 方法
    """

    name: str = 'NAS_DEFAULT'              # 子类必须覆盖

    def __init__(self):
        # 确保项目根目录在 sys.path（让子模块的 import 都能找到）
        project_root = self.get_project_root()
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        self.logger = get_logger(self.name)
        self.config = load_config()
        self.proxies: list = self.config.get('proxy_domains', [])
        self.timeout: int = self.config.get('request_timeout', 15)

    @staticmethod
    def get_project_root() -> str:
        """获取项目根目录（包含 server/ 目录的目录）"""
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def output_path(self, sub_dir: str, file_name: str = '') -> str:
        """构造 output 目录下的文件路径"""
        base = os.path.join(self.get_project_root(), 'server', 'output', sub_dir)
        if file_name:
            return os.path.join(base, file_name)
        return base

    def build_proxied_url(self, base_url: str, proxy_idx: Optional[int] = None) -> str:
        """构造通过代理转发的 URL"""
        if proxy_idx is not None and 0 <= proxy_idx < len(self.proxies):
            return self.proxies[proxy_idx] + '/' + base_url
        return base_url

    def run(self, schedule_time: str) -> None:
        """
        运行调度器：立即执行一次 + 每天定时执行

        Args:
            schedule_time: HH:MM 格式时间字符串
        """
        self.sync()
        schedule.every().day.at(schedule_time).do(self.sync)

        while True:
            schedule.run_pending()
            time.sleep(30)

    def sync(self) -> bool:
        """子类必须实现：执行一次同步逻辑"""
        raise NotImplementedError("子类必须实现 sync() 方法")