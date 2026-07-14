import re
import shutil
import subprocess
import sys
import socket
import requests
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Optional

from iptv_utils import IPTV_CONFIG

socket.setdefaulttimeout(5)
requests.packages.urllib3.disable_warnings()


@dataclass
class CheckerConfig:
    CONNECTIONS_PER_HOST: int = 5
    FFMPEG_PROCESS_TIMEOUT: int = 5
    FFMPEG_PROBESIZE: str = '128000'
    FFMPEG_ANALYZEDURATION: str = '1000000'


class IPTVChecker:
    _ffmpeg_available: Optional[bool] = None

    def __init__(self, user_agent: str = "okHttp/Mod-1.5.0.0", fps_min: int = 20, bitrate_min: int = 1000,
                 timeout_basic: int = IPTV_CONFIG.HTTP_TIMEOUT, timeout_fluent: int = IPTV_CONFIG.FFMPEG_TIMEOUT,
                 width_min: int = IPTV_CONFIG.MIN_RESOLUTION_WIDTH,
                 height_min: int = IPTV_CONFIG.MIN_RESOLUTION_HEIGHT):
        self.user_agent = user_agent
        self.fps_min = fps_min
        self.bitrate_min = bitrate_min
        self.width_min = width_min
        self.height_min = height_min
        self.timeout_basic = timeout_basic
        self.timeout_fluent = timeout_fluent
        self._session = requests.Session()

        self._session.headers.update({'User-Agent': self.user_agent})
        adapter = requests.adapters.HTTPAdapter(pool_connections=CheckerConfig.CONNECTIONS_PER_HOST, pool_maxsize=50, max_retries=0)
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)

    @classmethod
    def is_ffmpeg_available(cls) -> bool:
        if cls._ffmpeg_available is None:
            cls._ffmpeg_available = shutil.which('ffmpeg') is not None
        return cls._ffmpeg_available

    def _build_ffmpeg_cmd(self, url: str, mode: str = 'error') -> list:
        duration = '1' if mode == 'error' else '3'
        timeout_ms = (self.timeout_basic if mode == 'error' else self.timeout_fluent) * 1000000
        return [
            'ffmpeg', '-user_agent', self.user_agent, '-i', url,
            '-timeout', str(timeout_ms), '-http_seekable', '0',
            '-probesize', CheckerConfig.FFMPEG_PROBESIZE,
            '-analyzeduration', CheckerConfig.FFMPEG_ANALYZEDURATION,
            '-t', duration, '-f', 'null', '-', '-v', mode,
            '-hide_banner', '-loglevel', 'repeat+info', '-nostdin', '-threads', '1'
        ]

    def _parse_fps_bitrate(self, stderr: str) -> tuple[float, int, tuple[int, int], bool]:
        error_log = stderr.lower()
        has_video = 'video:' in error_log
        fps = 0.0
        bitrate = 0
        width = 0
        height = 0
        if has_video:
            res_match = re.search(r'video:[\s\S]{0,100}?(\d{3,4})x(\d{3,4})', error_log)
            if res_match:
                width, height = int(res_match.group(1)), int(res_match.group(2))
            fps_match = re.search(r'r_frame_rate=(\d+/\d+)|(\d+\.?\d*)\s+fps', error_log, re.IGNORECASE)
            if fps_match:
                fps_str = fps_match.group(1) or fps_match.group(2)
                try:
                    if '/' in fps_str:
                        n, d = map(int, fps_str.split('/'))
                        fps = n / d if d > 0 else 0.0
                    else:
                        fps = float(fps_str)
                except (ValueError, ZeroDivisionError):
                    pass
        variant = re.search(r'variant_bitrate\s*:\s*(\d+)', error_log)
        if variant:
            br = int(variant.group(1)) // 1000
            if br > 0:
                return fps, br, (width, height), has_video
        video_br = re.search(r'(?:stream #0:\d+:[\s\S]{0,100}?video:|Video:)[\s\S]{0,100}?(\d+)\s*kb/s', error_log)
        if video_br:
            br = int(video_br.group(1))
            if br > 200:
                return fps, br, (width, height), has_video
        stream_br = re.search(r'(\d+)k\s*\(', error_log)
        if stream_br:
            return fps, int(stream_br.group(1)), (width, height), has_video
        output_br = re.search(r'bitrate=([\d.]+)kbits/s', error_log)
        if output_br:
            try:
                bitrate = int(float(output_br.group(1)))
            except ValueError:
                pass
        return fps, bitrate, (width, height), has_video

    def _http_health_check(self, url: str) -> dict:
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return {'available': False, 'error': 'invalid_url'}
            headers = {'User-Agent': self.user_agent, 'Range': 'bytes=0-1024'}
            response = self._session.get(url, timeout=2, allow_redirects=True, verify=False, headers=headers, stream=True)
            if response.status_code >= 400:
                return {'available': False, 'error': f'status_{response.status_code}'}
            return {'available': True, 'error': None}
        except requests.exceptions.Timeout:
            return {'available': False, 'error': 'http_timeout'}
        except requests.exceptions.ConnectionError:
            return {'available': False, 'error': 'http_connection_error'}
        except requests.exceptions.TooManyRedirects:
            return {'available': False, 'error': 'http_too_many_redirects'}
        except requests.exceptions.RequestException as e:
            return {'available': False, 'error': f'http_request_error_{str(e)[:30]}'}
        except Exception as e:
            return {'available': False, 'error': f'http_unknown_error_{str(e)[:30]}'}

    def _stream_availability_check(self, url: str) -> dict:
        cmd = self._build_ffmpeg_cmd(url, 'error')
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                       creationflags=creationflags, start_new_session=True)
            try:
                stderr = process.communicate(timeout=CheckerConfig.FFMPEG_PROCESS_TIMEOUT)[1]
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {'available': False, 'error': 'ffmpeg_timeout'}
            err_key = self._get_ffmpeg_error_keyword(stderr)
            if err_key:
                return {'available': False, 'error': f'ffmpeg_error_{err_key}'}
            has_video = 'video:' in stderr.lower()
            if process.returncode in (0, 1) and has_video:
                return {'available': True, 'error': None}
            if has_video and process.returncode == 2:
                return {'available': True, 'error': None}
            if not has_video and process.returncode in (0, 1):
                return {'available': False, 'error': 'no_video_stream'}
            return {'available': False, 'error': f'ffmpeg_returncode_{process.returncode}'}
        except Exception as e:
            return {'available': False, 'error': f'exception_{type(e).__name__}'}

    def _get_ffmpeg_error_keyword(self, stderr: str) -> str:
        error_log = stderr.lower()
        mapping = {
            '404': 'not_found_404', 'not found': 'not_found', 'file not found': 'file_not_found',
            'connection refused': 'connection_refused', 'connection reset': 'connection_reset',
            'connection timeout': 'connection_timeout', 'connection timed out': 'connection_timeout',
            'unable to open': 'unable_to_open', 'server returned 403': 'forbidden_403',
            'invalid data': 'invalid_data', 'could not find codec': 'codec_not_found',
            'invalid codec': 'invalid_codec', 'stream not found': 'stream_not_found',
            'could not open codec': 'codec_open_failed', 'protocol not found': 'protocol_not_found',
            'no such file': 'file_not_found', 'http error': 'http_error',
            'server error': 'server_error', 'bad data': 'bad_data',
            'operation not permitted': 'permission_denied'
        }
        for kw, err_type in mapping.items():
            if kw in error_log:
                return err_type
        return None

    def _stream_quality_check(self, url: str) -> dict:
        cmd = self._build_ffmpeg_cmd(url, 'verbose')
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                       creationflags=creationflags, start_new_session=True)
            try:
                stderr = process.communicate(timeout=self.timeout_fluent)[1]
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {'fluent': False, 'fps': None, 'bitrate': None, 'resolution': None, 'error': 'timeout'}
            error_log = stderr.lower()
            fps, bitrate, (width, height), has_video = self._parse_fps_bitrate(stderr)
            lag_keywords = ['packet loss', 'frame drop', 'buffer underflow', 'read error']
            if any(kw in error_log for kw in lag_keywords):
                return {'fluent': False, 'fps': fps if fps > 0 else None, 'bitrate': bitrate if bitrate > 0 else None,
                        'resolution': (width, height) if has_video else None, 'error': 'stream_lag'}
            if has_video:
                if width == 0 or height == 0:
                    return {'fluent': False, 'fps': fps if fps > 0 else None, 'bitrate': bitrate if bitrate > 0 else None,
                            'resolution': None, 'error': 'resolution_not_detected'}
                is_valid = (width >= self.width_min and height >= self.height_min) or (width >= self.height_min and height >= self.width_min)
                if not is_valid:
                    return {'fluent': False, 'fps': fps if fps > 0 else None, 'bitrate': bitrate if bitrate > 0 else None,
                            'resolution': (width, height), 'error': f'resolution_too_low: {width}x{height}'}
                if fps > 0 and fps < self.fps_min:
                    return {'fluent': False, 'fps': fps, 'bitrate': bitrate if bitrate > 0 else None,
                            'resolution': (width, height), 'error': f'fps_too_low: {fps:.2f}'}
                if bitrate > 0 and bitrate < self.bitrate_min:
                    return {'fluent': False, 'fps': fps if fps > 0 else None, 'bitrate': bitrate,
                            'resolution': (width, height), 'error': f'bitrate_too_low: {bitrate}'}
            if not has_video:
                return {'fluent': False, 'fps': None, 'bitrate': None, 'resolution': None, 'error': 'no_video_stream'}
            stream_err = ['404', 'not found', 'connection refused', 'connection timeout',
                          'unable to open', 'server returned 403', 'invalid data']
            if any(kw in error_log for kw in stream_err):
                return {'fluent': False, 'fps': None, 'bitrate': None, 'resolution': None, 'error': 'stream_error'}
            return {'fluent': True, 'fps': fps if fps > 0 else None, 'bitrate': bitrate if bitrate > 0 else None,
                    'resolution': (width, height), 'error': None}
        except Exception as e:
            return {'fluent': False, 'fps': None, 'bitrate': None, 'resolution': None, 'error': f'unknown_error: {str(e)}'}

    def check(self, url: str) -> dict:
        http_check = self._http_health_check(url)
        if not http_check['available']:
            return {'available': False, 'fluent': False, 'fps': None, 'bitrate': None, 'error': http_check['error']}
        avail_check = self._stream_availability_check(url)
        if not avail_check.get('available', False):
            return {'available': False, 'fluent': False, 'fps': None, 'bitrate': None,
                    'error': avail_check.get('error', 'invalid_stream_format')}
        quality = self._stream_quality_check(url)
        return {'available': True, 'fluent': quality['fluent'], 'fps': quality['fps'],
                'bitrate': quality['bitrate'], 'error': quality['error']}
