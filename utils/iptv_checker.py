"""
IPTV 频道检测工具类

提供单个 URL 的可用性和流畅度检测功能（优化版）
"""

import re
import shutil
import subprocess
import sys
import socket
import requests
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Optional
import multiprocessing

# 全局配置：优化网络和子进程参数
socket.setdefaulttimeout(5)  # 全局 socket 超时
requests.packages.urllib3.disable_warnings()  # 禁用 SSL 警告

@dataclass
class CheckerConfig:
    """检测配置常量（集中管理优化参数）"""
    # 网络层优化
    CONNECTIONS_PER_HOST: int = 5  # 单主机最大连接数
    # FFmpeg 优化
    FFMPEG_PROCESS_TIMEOUT: int = 5  # ffmpeg 进程硬超时（秒）- 增加到 5 秒
    FFMPEG_PROBESIZE: str = '128000'  # 进一步减小探测大小（128KB）
    FFMPEG_ANALYZEDURATION: str = '1000000'  # 进一步缩短分析时长（1 秒）
    # 并发优化
    MAX_WORKERS_RATIO: float = 1.5  # 基于 CPU 核心数的并发系数
    BATCH_SIZE: int = 500  # 批量处理大小
    # 快速过滤优化
    SKIP_INVALID_SCHEMES: tuple = ('file', 'ftp', 'mailto')  # 跳过的协议
    MIN_CONTENT_LENGTH: int = 50  # 最小内容长度阈值

class IPTVChecker:
    """IPTV 频道检测器（优化版）"""

    # 类变量：ffmpeg 可用性缓存
    _ffmpeg_available: Optional[bool] = None

    def __init__(
        self,
        user_agent: str = "okHttp/Mod-1.5.0.0",
        fps_min: int = 20,
        bitrate_min: int = 1000,
        timeout_basic: int = 8,
        timeout_fluent: int = 15,
        max_workers: int = None
    ):
        """
        初始化检测器

        Args:
            user_agent: HTTP User-Agent
            fps_min: 最小帧率阈值
            bitrate_min: 最小码率阈值 (kbps)
            timeout_basic: 基础检测超时时间（秒）
            timeout_fluent: 流畅检测超时时间（秒）
            max_workers: 默认最大并发数（自动适配 CPU 核心数）
        """
        self.user_agent = user_agent
        self.fps_min = fps_min
        self.bitrate_min = bitrate_min
        self.timeout_basic = timeout_basic
        self.timeout_fluent = timeout_fluent
        
        # 自动计算最优并发数（适配 10w+ 量级）
        if max_workers is None:
            cpu_count = multiprocessing.cpu_count()
            self.max_workers = min(int(cpu_count * CheckerConfig.MAX_WORKERS_RATIO), 100)
        else:
            self.max_workers = max_workers

        # 初始化 requests 会话池（复用连接）
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': self.user_agent})
        self._session.mount('http://', requests.adapters.HTTPAdapter(
            pool_connections=CheckerConfig.CONNECTIONS_PER_HOST,
            pool_maxsize=50,
            max_retries=0  # 禁用重试（快速失败）
        ))
        self._session.mount('https://', requests.adapters.HTTPAdapter(
            pool_connections=CheckerConfig.CONNECTIONS_PER_HOST,
            pool_maxsize=50,
            max_retries=0
        ))

    @classmethod
    def is_ffmpeg_available(cls) -> bool:
        """检查 FFmpeg 是否可用（缓存结果）"""
        if cls._ffmpeg_available is None:
            cls._ffmpeg_available = shutil.which('ffmpeg') is not None
        return cls._ffmpeg_available

    def _build_ffmpeg_cmd(self, url: str, mode: str = 'error') -> list:
        """
        构建优化的 ffmpeg 检测命令（补充关键参数）

        Args:
            url: 检测 URL
            mode: 日志模式 ('error' 或 'verbose')

        Returns:
            ffmpeg 命令列表
        """
        # 极致优化：进一步缩短检测时长
        duration = '1' if mode == 'error' else '3'  # 从 2/5 秒缩短到 1/3 秒
        timeout_ms = (self.timeout_basic if mode == 'error' else self.timeout_fluent) * 1000000
        
        return [
            'ffmpeg',
            '-user_agent', self.user_agent,
            '-i', url,
            '-timeout', str(timeout_ms),      # FFmpeg 内置超时（微秒）
            '-http_seekable', '0',            # 禁用 HTTP Seek，适配直播源
            '-probesize', CheckerConfig.FFMPEG_PROBESIZE,  # 极致优化：128KB
            '-analyzeduration', CheckerConfig.FFMPEG_ANALYZEDURATION,  # 极致优化：1秒
            '-t', duration,
            '-f', 'null', '-',
            '-v', mode,
            '-hide_banner',
            '-loglevel', 'repeat+info',       # 避免重复日志干扰
            '-nostdin',                       # 禁用标准输入（防止阻塞）
            '-threads', '1'                   # 单线程（减少资源占用）
        ]

    def _check_ffmpeg_error(self, stderr: str) -> bool:
        """
        检查 ffmpeg 严重错误

        Args:
            stderr: ffmpeg 错误输出

        Returns:
            是否包含严重错误
        """
        error_log = stderr.lower()
        # 扩展错误关键词（提升准确性）
        keywords = [
            '404', 'not found', 'file not found',
            'connection refused', 'connection reset',
            'connection timeout', 'connection timed out',
            'unable to open', 'server returned 403 forbidden',
            'invalid data found when processing input',
            'could not find codec parameters', 'invalid codec parameters',
            'stream not found', 'could not open codec',
            'protocol not found', 'no such file or directory'
        ]
        return any(keyword in error_log for keyword in keywords)

    def _parse_fps_bitrate(self, stderr: str) -> tuple[float, int, tuple[int, int], bool]:
        """
        解析帧率、码率、分辨率，判断视频流类型（优化版）
        
        注意：只检测视频流，不检测音频

        Returns:
            (fps, bitrate, (width, height), has_video)
        """
        # 预编译正则表达式（类级别缓存，提升性能）
        error_log = stderr.lower()
        has_video = 'video:' in error_log
        fps = 0.0
        bitrate = 0
        width = 0
        height = 0

        # 1. 解析分辨率（优先匹配，只需一次）
        if has_video:
            resolution_match = re.search(r'video:[\s\S]{0,100}?(\d{3,4})x(\d{3,4})', error_log)
            if resolution_match:
                width = int(resolution_match.group(1))
                height = int(resolution_match.group(2))
        
        # 2. 解析帧率（优化：合并正则匹配）
        if has_video:
            fps_match = re.search(r'r_frame_rate=(\d+/\d+)|(\d+\.?\d*)\s+fps', error_log, re.IGNORECASE)
            if fps_match:
                fps_str = fps_match.group(1) or fps_match.group(2)
                try:
                    if '/' in fps_str:
                        num, den = map(int, fps_str.split('/'))
                        fps = num / den if den > 0 else 0.0
                    else:
                        fps = float(fps_str)
                except (ValueError, ZeroDivisionError):
                    pass

        # 3. 解析码率（优化：减少重复匹配，提前返回）
        # HLS 流特殊处理：优先匹配 variant_bitrate
        variant_bitrate = re.search(r'variant_bitrate\s*:\s*(\d+)', error_log)
        if variant_bitrate:
            br = int(variant_bitrate.group(1)) // 1000
            if br > 0:
                bitrate = br
                return fps, bitrate, (width, height), has_video  # 提前返回
        
        # 输入流视频码率（最准确）
        # 格式：Stream #0:0: Video: h264, 1920x1080, 25 fps, 3000 kb/s
        # 或：Video: h264, 1920x1080, 25 fps, 5000 kb/s
        video_stream_bitrate = re.search(r'(?:stream #0:\d+:[\s\S]{0,100}?video:|Video:)[\s\S]{0,100}?(\d+)\s*kb/s', error_log)
        if video_stream_bitrate:
            br = int(video_stream_bitrate.group(1))
            if br > 200:
                bitrate = br
                return fps, bitrate, (width, height), has_video  # 提前返回
        
        # 视频流信息中的码率（兜底）
        stream_bitrate = re.search(r'(\d+)k\s*\(', error_log)
        if stream_bitrate:
            bitrate = int(stream_bitrate.group(1))
            return fps, bitrate, (width, height), has_video  # 提前返回
        
        # 从最终输出中计算平均码率
        output_bitrate = re.search(r'bitrate=([\d.]+)kbits/s', error_log)
        if output_bitrate:
            try:
                bitrate = int(float(output_bitrate.group(1)))
            except ValueError:
                pass

        return fps, bitrate, (width, height), has_video

    def _http_health_check(self, url: str) -> dict:
        """
        第一重检测：HTTP 健康检查
        
        通过 HTTP HEAD 请求快速判断 URL 是否可达
        
        优化策略：
        1. 超时时间 2 秒
        2. 禁用重定向，避免重定向耗时
        3. 只检查明显错误（4xx, 5xx），其他一律通过
        4. HEAD 失败不重试 GET，直接标记为可能有效

        Args:
            url: 检测 URL

        Returns:
            检查结果字典，包含：
            - available: 是否通过快速检查
            - error: 错误信息
        """
        try:
            # 1. 基础 URL 格式检查（超快）
            parsed = urlparse(url)
            if not parsed.netloc:
                return {'available': False, 'error': 'invalid_url'}

            # 2. 快速 HEAD 请求（不下载内容）
            # 优化：使用会话池，复用连接
            if not hasattr(self, '_session'):
                self._session = requests.Session()
                self._session.verify = False
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=100,
                    pool_maxsize=100,
                    pool_block=False
                )
                self._session.mount('http://', adapter)
                self._session.mount('https://', adapter)

            # 优化：使用 GET 但限制只获取少量内容（某些服务器对 HEAD 返回错误但 GET 正常）
            headers = {
                'User-Agent': self.user_agent,
                'Range': 'bytes=0-1024'  # 只获取前 1KB
            }
            response = self._session.get(
                url,
                timeout=2, 
                allow_redirects=True,  # 允许重定向
                verify=False,
                headers=headers,
                stream=True  # 不下载完整内容
            )

            # 3. 状态码检查（非常宽松：只拒绝 4xx 和 5xx 错误）
            # 2xx, 3xx 都算通过
            if response.status_code >= 400:
                return {'available': False, 'error': f'status_{response.status_code}'}

            # 所有检查通过
            return {'available': True, 'error': None}

        except requests.exceptions.Timeout:
            # 超时：记录具体错误
            return {'available': False, 'error': 'timeout'}
        except requests.exceptions.ConnectionError:
            return {'available': False, 'error': 'connection_error'}
        except requests.exceptions.TooManyRedirects:
            # 重定向过多
            return {'available': False, 'error': 'too_many_redirects'}
        except requests.exceptions.RequestException as e:
            # 其他请求异常
            return {'available': False, 'error': f'request_error_{str(e)[:30]}'}
        except Exception as e:
            # 未知异常
            return {'available': False, 'error': f'unknown_error_{str(e)[:30]}'}


    def _stream_availability_check(self, url: str) -> dict:
        """
        第二重检测：视频流可用性检查
        
        使用 FFmpeg 探测视频流格式，验证是否为有效的 M3U8/TS 流
        
        注意：能通过第一重检测的 URL 已经是有效的 http/https 协议

        Args:
            url: 检测 URL

        Returns:
            包含是否可用和详细错误信息的字典
        """
        # 注意：不需要再检查 scheme，第一重已经过滤了无效协议
        # 直接进行 FFmpeg 检测
        cmd = self._build_ffmpeg_cmd(url, 'error')

        try:
            # 优化：使用 DEVNULL 减少 IO 开销，设置 creationflags 减少进程创建开销
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW  # Windows 隐藏窗口
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                start_new_session=True  # 独立会话（防止进程僵死）
            )

            try:
                # 双重超时保护：硬超时 + 软超时
                stderr = process.communicate(timeout=CheckerConfig.FFMPEG_PROCESS_TIMEOUT)[1]
            except subprocess.TimeoutExpired:
                # 强制终止进程（防止僵尸进程）
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {'available': False, 'error': 'ffmpeg_timeout', 'detail': 'FFmpeg 检测超时'}

            # 检测严重错误
            error_keyword = self._get_ffmpeg_error_keyword(stderr)
            if error_keyword:
                return {'available': False, 'error': f'ffmpeg_error_{error_keyword}', 'detail': stderr[:200]}

            # 检查是否有视频流信息
            has_video = 'video:' in stderr.lower()
            
            # 兼容 FFmpeg 返回码 1（轻微警告但流有效）
            if process.returncode in (0, 1):
                if has_video:
                    return {'available': True, 'error': None}
                else:
                    return {'available': False, 'error': 'no_video_stream', 'detail': '未检测到视频流'}

            # 返回码 2 可能某些流特殊情况
            if has_video and process.returncode == 2:
                return {'available': True, 'error': None}

            # 其他返回码视为无效
            return {'available': False, 'error': f'ffmpeg_returncode_{process.returncode}', 'detail': f'FFmpeg 返回码: {process.returncode}'}

        except Exception as e:
            return {'available': False, 'error': 'exception', 'detail': str(e)[:50]}
        
        return {'available': False, 'error': 'unknown', 'detail': '未知错误'}

    def _get_ffmpeg_error_keyword(self, stderr: str) -> str:
        """
        获取 FFmpeg 错误的关键词

        Args:
            stderr: FFmpeg 错误输出

        Returns:
            错误关键词，如果没有错误返回 None
        """
        error_log = stderr.lower()
        
        error_keywords = {
            '404': 'not_found_404',
            'not found': 'not_found',
            'file not found': 'file_not_found',
            'connection refused': 'connection_refused',
            'connection reset': 'connection_reset',
            'connection timeout': 'connection_timeout',
            'connection timed out': 'connection_timeout',
            'unable to open': 'unable_to_open',
            'server returned 403': 'forbidden_403',
            'invalid data': 'invalid_data',
            'could not find codec': 'codec_not_found',
            'invalid codec': 'invalid_codec',
            'stream not found': 'stream_not_found',
            'could not open codec': 'codec_open_failed',
            'protocol not found': 'protocol_not_found',
            'no such file': 'file_not_found',
            'http error': 'http_error',
            'server error': 'server_error',
            'bad data': 'bad_data',
            'operation not permitted': 'permission_denied',
        }
        
        for keyword, error_type in error_keywords.items():
            if keyword in error_log:
                return error_type
        
        return None

    def _stream_quality_check(self, url: str) -> dict:
        """
        第三重检测：视频流质量检查
        
        使用 FFmpeg 分析视频流质量指标（帧率、码率、卡顿）
        
        注意：能通过前两重检测的 URL 已经是有效的 http/https 协议

        Args:
            url: 检测 URL

        Returns:
            检测结果字典，包含：
            - fluent: 是否流畅
            - fps: 帧率（如果检测到）
            - bitrate: 码率（如果检测到）
            - resolution: 分辨率（如果检测到）
            - error: 错误信息（如果有）
        """
        # 注意：不需要再检查 scheme，前两重已经过滤了无效协议
        # 直接进行 FFmpeg 质量检测
        cmd = self._build_ffmpeg_cmd(url, 'verbose')

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                start_new_session=True
            )

            try:
                stderr = process.communicate(timeout=self.timeout_fluent)[1]
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {
                    'fluent': False,
                    'fps': None,
                    'bitrate': None,
                    'resolution': None,
                    'error': 'timeout'
                }

            error_log = stderr.lower()
            fps, bitrate, (width, height), has_video = self._parse_fps_bitrate(stderr)

            # 1. 快速失败：检测严重错误（优先检查，避免后续计算）
            if 'packet loss' in error_log or 'frame drop' in error_log or \
               'buffer underflow' in error_log or 'read error' in error_log:
                return {
                    'fluent': False,
                    'fps': fps if fps > 0 else None,
                    'bitrate': bitrate if bitrate > 0 else None,
                    'resolution': (width, height) if has_video else None,
                    'error': 'stream_lag'
                }

            # 2. 视频源检测（优化：提前计算分辨率判断）
            if has_video:
                # 3.1 分辨率检测
                if width == 0 or height == 0:
                    return {
                        'fluent': False,
                        'fps': fps if fps > 0 else None,
                        'bitrate': bitrate if bitrate > 0 else None,
                        'resolution': None,
                        'error': 'resolution_not_detected'
                    }
                
                # 3.2 分辨率快速判断（使用位运算优化）
                # 横屏：width >= 1920 and height >= 1080
                # 竖屏：width >= 1080 and height >= 1920
                is_valid_resolution = (width >= 1920 and height >= 1080) or \
                                     (width >= 1080 and height >= 1920)
                if not is_valid_resolution:
                    return {
                        'fluent': False,
                        'fps': fps if fps > 0 else None,
                        'bitrate': bitrate if bitrate > 0 else None,
                        'resolution': (width, height),
                        'error': f'resolution_too_low: {width}x{height}'
                    }

                # 3.3 帧率检测（使用直接比较）
                if fps > 0 and fps < self.fps_min:
                    return {
                        'fluent': False,
                        'fps': fps,
                        'bitrate': bitrate if bitrate > 0 else None,
                        'resolution': (width, height),
                        'error': f'fps_too_low: {fps:.2f}'
                    }

                # 3.4 码率检测（使用直接比较）
                if bitrate > 0 and bitrate < self.bitrate_min:
                    return {
                        'fluent': False,
                        'fps': fps if fps > 0 else None,
                        'bitrate': bitrate,
                        'resolution': (width, height),
                        'error': f'bitrate_too_low: {bitrate}'
                    }

            # 4. 基础错误检测（优化：使用 in 操作符直接判断）
            if '404' in error_log or 'not found' in error_log or \
               'connection refused' in error_log or 'connection timeout' in error_log or \
               'unable to open' in error_log or 'server returned 403' in error_log or \
               'invalid data' in error_log:
                return {
                    'fluent': False,
                    'fps': None,
                    'bitrate': None,
                    'resolution': None,
                    'error': 'stream_error'
                }

            # 5. 兜底判断：无严重错误即认为流畅
            return {
                'fluent': True,
                'fps': fps if fps > 0 else None,
                'bitrate': bitrate if bitrate > 0 else None,
                'resolution': (width, height) if has_video else None,
                'error': None
            }

        except Exception as e:
            return {
                'fluent': False,
                'fps': None,
                'bitrate': None,
                'resolution': None,
                'error': f'unknown_error: {str(e)}'
            }
    
    def _build_error_result(self, available: bool, fluent: bool, error: str) -> dict:
        """
        构建错误结果字典
        
        Args:
            available: 是否可用
            fluent: 是否流畅
            error: 错误信息
        
        Returns:
            标准化的错误结果字典
        """
        return {
            'available': available,
            'fluent': fluent,
            'fps': None,
            'bitrate': None,
            'error': error
        }


    def check(self, url: str) -> dict:
        """
        完整检测视频源（三重检测机制）
        
        检测流程：
        1. 第一重：HTTP 快速检查（状态码、连接性）
        2. 第二重：FFmpeg 可用性检查（视频流格式验证）
        3. 第三重：FFmpeg 流畅度检查（帧率、码率分析）

        Args:
            url: 检测 URL

        Returns:
            检测结果字典，包含：
            - available: 是否可用（通过前两重检测）
            - fluent: 是否流畅（通过第三重检测）
            - fps: 帧率（仅第三重检测通过时有效）
            - bitrate: 码率（仅第三重检测通过时有效，单位：kbps）
            - error: 错误信息（失败时包含具体原因）
        """
        # ========== 第一重：HTTP 快速检查 ==========
        # 目的：快速过滤明显失效的 URL（4xx/5xx 错误、连接失败等）
        # 特点：速度快（~1 秒），无需 FFmpeg
        http_check = self._http_health_check(url)
        if not http_check['available']:
            return self._build_error_result(
                available=False,
                fluent=False,
                error=http_check['error']
            )
        
        # ========== 第二重：FFmpeg 可用性检查 ==========
        # 目的：验证视频流格式是否正确（M3U8/TS 等）
        # 特点：需要 FFmpeg，耗时中等（~3-5 秒）
        availability_check = self._stream_availability_check(url)
        if not availability_check.get('available', False):
            return self._build_error_result(
                available=False,
                fluent=False,
                error=availability_check.get('error', 'invalid_stream_format')
            )
        
        # ========== 第三重：FFmpeg 流畅度检查 ==========
        # 目的：分析视频质量（帧率、码率、卡顿情况）
        # 特点：需要 FFmpeg，耗时较长（~5-10 秒）
        quality_check = self._stream_quality_check(url)
        
        return {
            'available': True,
            'fluent': quality_check['fluent'],
            'fps': quality_check['fps'],
            'bitrate': quality_check['bitrate'],
            'error': quality_check['error']
        }
  

if __name__ == "__main__":
    # 测试示例
    test_url = "http://192.168.1.12:8015/migu/608807420"

    print(f"测试 URL: {test_url}")
    print("-" * 60)

    checker = IPTVChecker()
    result = checker.check(test_url)  # 修正：原测试代码调用错误（check_channel 返回 Channel 对象，不是字典）

    print(f"可用性：{'✓' if result['available'] else '✗'}")
    print(f"流畅度：{'✓' if result['fluent'] else '✗'}")
    print(f"帧  率：{result['fps']:.2f} fps" if result['fps'] else "帧  率：未检测到")
    print(f"码  率：{result['bitrate']} kbps" if result['bitrate'] else "码  率：未检测到")
    print(f"错  误：{result['error']}" if result['error'] else "错  误：无")