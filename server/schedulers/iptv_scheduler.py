"""
IPTV Scheduler - IPTV 订阅同步

每天下载一次 IPTV 播放列表（m3u），原样保存。
"""
import os
import requests

from server.utils.scheduler_base import SchedulerBase
from server.utils.text_downloader import fetch_text


class IptvScheduler(SchedulerBase):
    name = 'NAS_IPTV'

    def __init__(self):
        super().__init__()
        self.cfg = self.config['iptv']
        self.source_url: str = self.cfg['source_url']
        self.use_proxy: bool = self.cfg.get('use_proxy', False)
        self.output_dir: str = self.output_path(self.cfg['output_dir'])
        self.output_file: str = os.path.join(self.output_dir, self.cfg['output_file'])

    def sync(self) -> bool:
        if self.use_proxy:
            attempts = list(range(len(self.proxies)))
        else:
            attempts = [None]

        for idx in attempts:
            url = self.build_proxied_url(self.source_url, idx) if idx is not None else self.source_url
            label = f" (代理 {idx + 1}/{len(attempts)})" if self.use_proxy and idx and idx > 0 else ""

            content = fetch_text(url, timeout=self.timeout)
            if content is not None:
                os.makedirs(self.output_dir, exist_ok=True)
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logger.info(f"IPTV 配置已同步到 {self.output_file}")
                return True

            # 失败处理
            is_last = idx == attempts[-1]
            if is_last:
                self.logger.error("IPTV 配置同步失败 (已用完全部代理)")
                return False
            self.logger.warning(f"同步失败{label}，切换代理...")

        return False


def run():
    scheduler = IptvScheduler()
    scheduler.run(scheduler.cfg['schedule_time'])


if __name__ == "__main__":
    run()