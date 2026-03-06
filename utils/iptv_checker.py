"""
IPTV 频道检测工具类

提供单个 URL 的可用性和流畅度检测功能（优化版）
"""

import logging
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Union, Callable

# 延迟导入避免循环依赖
try:
    from models.channel import Channel, CheckResult
except ImportError:
    Channel = None
    CheckResult = None

class IPTVChecker:
    """IPTV 频道检测器（优化版）"""

    # 类变量：ffmpeg 可用性缓存
    _ffmpeg_available: Optional[bool] = None

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        fps_min: int = 20,
        bitrate_min: int = 1000,
        timeout_basic: int = 8,
        timeout_fluent: int = 15,
        max_workers: int = 30
    ):
        """
        初始化检测器

        Args:
            user_agent: HTTP User-Agent
            fps_min: 最小帧率阈值
            bitrate_min: 最小码率阈值 (kbps)
            timeout_basic: 基础检测超时时间（秒）
            timeout_fluent: 流畅检测超时时间（秒）
            max_workers: 默认最大并发数
        """
        self.user_agent = user_agent
        self.fps_min = fps_min
        self.bitrate_min = bitrate_min
        self.timeout_basic = timeout_basic
        self.timeout_fluent = timeout_fluent
        self.max_workers = max_workers

    @classmethod
    def is_ffmpeg_available(cls) -> bool:
        """
        检查 ffmpeg 是否可用
        
        Returns:
            bool: ffmpeg 是否可用
        """
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
        # 优化：缩短检测时长，提升速度
        duration = '2' if mode == 'error' else '5'  # 从 3/8 秒缩短到 2/5 秒
        timeout_ms = (self.timeout_basic if mode == 'error' else self.timeout_fluent) * 1000000
        
        return [
            'ffmpeg',
            '-user_agent', self.user_agent,
            '-i', url,
            '-timeout', str(timeout_ms),      # FFmpeg 内置超时（微秒）
            '-http_seekable', '0',            # 禁用 HTTP Seek，适配直播源
            '-probesize', '256000',           # 优化：减小探测大小（512KB->256KB）
            '-analyzeduration', '3000000',    # 优化：缩短分析时长（5 秒->3 秒）
            '-t', duration,
            '-f', 'null', '-',
            '-v', mode,
            '-hide_banner',
            '-loglevel', 'repeat+info'        # 避免重复日志干扰
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
        keywords = [
            '404', 'not found', 'file not found',
            'connection refused',
            'connection timeout', 'connection timed out',
            'unable to open', 'server returned 403 forbidden',
            'invalid data found when processing input'
        ]
        return any(keyword in error_log for keyword in keywords)

    def _parse_fps_bitrate(self, stderr: str) -> tuple[float, int, bool, bool]:
        """
        解析帧率、码率，判断音视频类型

        Returns:
            (fps, bitrate, has_video, has_audio)
        """
        error_log = stderr.lower()
        has_video = 'video:' in error_log
        has_audio = 'audio:' in error_log
        fps = 0.0
        bitrate = 0

        # 1. 解析帧率（兼容分数格式：24000/1001 → 23.976）
        if has_video:
            # 优先匹配视频流原生帧率（最准确）
            fps_match = re.search(r'r_frame_rate=(\d+/\d+)', error_log) or \
                        re.search(r'(\d+\.?\d*)\s+fps', error_log, re.IGNORECASE)
            
            if fps_match:
                fps_str = fps_match.group(1)
                try:
                    if '/' in fps_str:
                        num, den = map(int, fps_str.split('/'))
                        fps = num / den if den > 0 else 0.0
                    else:
                        fps = float(fps_str)
                except (ValueError, ZeroDivisionError):
                    fps = 0.0

        # 2. 解析码率（多种格式兼容）
        # HLS 流特殊处理：优先匹配 variant_bitrate (单位 bps)
        # 例如：variant_bitrate : 2084544  (2084 kbps)
        variant_bitrate = re.search(r'variant_bitrate\s*:\s*(\d+)', error_log)
        if variant_bitrate:
            br = int(variant_bitrate.group(1)) // 1000  # 转换为 kbps
            # 只有当 variant_bitrate > 0 时才使用（某些流 variant_bitrate=0 表示未知）
            if br > 0:
                bitrate = br
        
        # 格式 1: 输入流视频码率（最准确）
        # Stream #0:0: Video: h264, 1920x1080, 25 fps, 25 tbr, 3000 kb/s
        # 注意：不要匹配输出流（Output #0）的码率，那是重新编码的目标码率，不准确
        if bitrate == 0:
            # 使用 [\s\S] 匹配换行符
            video_stream_bitrate = re.search(r'stream #0:\d+: video:[\s\S]{0,200}? (\d+) kb/s', error_log)
            if video_stream_bitrate:
                br = int(video_stream_bitrate.group(1))
                # 排除 FFmpeg 输出流的虚假码率（200kbps 是默认目标码率）
                if br > 200:
                    bitrate = br
        
        # 格式 1b: 输入流音频码率（如果视频流没有）
        # Stream #0:1: Audio: aac, 44100 Hz, stereo, 128 kb/s
        if bitrate == 0:
            audio_stream_bitrate = re.search(r'stream #0:\d+: audio:[\s\S]{0,200}? (\d+) kb/s', error_log)
            if audio_stream_bitrate:
                audio_br = int(audio_stream_bitrate.group(1))
                # 排除 FFmpeg 输出流的虚假码率
                if audio_br > 200:
                    if has_video:
                        bitrate = audio_br * 10  # 估算
                    else:
                        bitrate = audio_br
        
        # 格式 2: 视频流信息中的码率
        # 例如：Stream #0:0: Video: h264, 1920x1080, 25 fps, 25 tbr, 3000k (default)
        if bitrate == 0:
            stream_bitrate = re.search(r'(\d+)k\s*\(', error_log)
            if stream_bitrate:
                bitrate = int(stream_bitrate.group(1))
        
        # 格式 3: 从最终输出中计算平均码率
        # 例如：frame= 125 fps=25 q=-1.0 Lsize= 2048kB time=00:00:05.00 bitrate=3355.2kbits/s
        if bitrate == 0:
            output_bitrate = re.search(r'time=\d+:\d+:\d+\.\d+\s+bitrate=([\d.]+)kbits/s', error_log)
            if output_bitrate:
                try:
                    bitrate = int(float(output_bitrate.group(1)))
                except ValueError:
                    pass

        return fps, bitrate, has_video, has_audio

    def check_available(self, url: str) -> bool:
        """
        检查 URL 是否可用（基础检测，无重试）

        Args:
            url: 检测 URL

        Returns:
            是否可用
        """
        cmd = self._build_ffmpeg_cmd(url, 'error')

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                # 总超时留 2 秒缓冲
                _, stderr = process.communicate(timeout=self.timeout_basic + 2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return False

            # 检测严重错误
            if self._check_ffmpeg_error(stderr):
                return False

            # 兼容 FFmpeg 返回码 1（轻微警告但流有效）
            if process.returncode in (0, 1):
                return True

        except Exception:
            return False
        
        return False

    def check_fluent(self, url: str) -> dict:
        """
        检查 URL 是否流畅（流畅度检测，带帧率/码率/卡顿检测）

        Args:
            url: 检测 URL

        Returns:
            检测结果字典，包含：
            - fluent: 是否流畅
            - fps: 帧率（如果检测到）
            - bitrate: 码率（如果检测到）
            - error: 错误信息（如果有）
        """
        cmd = self._build_ffmpeg_cmd(url, 'verbose')

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                _, stderr = process.communicate(timeout=self.timeout_fluent)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return {
                    'fluent': False,
                    'fps': None,
                    'bitrate': None,
                    'error': 'timeout'
                }

            error_log = stderr.lower()
            fps, bitrate, has_video, has_audio = self._parse_fps_bitrate(stderr)

            # 1. 检测卡顿类错误
            lag_keywords = ['packet loss', 'frame drop', 'buffer underflow', 'read error']
            if any(keyword in error_log for keyword in lag_keywords):
                return {
                    'fluent': False,
                    'fps': fps if fps > 0 else None,
                    'bitrate': bitrate if bitrate > 0 else None,
                    'error': 'stream_lag'
                }

            # 2. 纯音频源判断（无需帧率检测，仅校验码率）
            if has_audio and not has_video:
                if bitrate > 0 and bitrate < self.bitrate_min // 10:  # 音频码率阈值降低
                    return {
                        'fluent': False,
                        'fps': None,
                        'bitrate': bitrate,
                        'error': f'bitrate_too_low: {bitrate}'
                    }
                return {
                    'fluent': True,
                    'fps': None,
                    'bitrate': bitrate if bitrate > 0 else None,
                    'error': None
                }

            # 3. 视频源帧率检测
            if has_video and fps > 0 and fps < self.fps_min:
                return {
                    'fluent': False,
                    'fps': fps,
                    'bitrate': bitrate if bitrate > 0 else None,
                    'error': f'fps_too_low: {fps:.2f}'
                }

            # 4. 视频源码率检测
            if has_video and bitrate > 0 and bitrate < self.bitrate_min:
                return {
                    'fluent': False,
                    'fps': fps if fps > 0 else None,
                    'bitrate': bitrate,
                    'error': f'bitrate_too_low: {bitrate}'
                }

            # 5. 基础错误检测
            basic_error_keywords = [
                '404', 'not found', 'connection refused', 'connection timeout',
                'unable to open', 'server returned 403', 'invalid data'
            ]
            if any(keyword in error_log for keyword in basic_error_keywords):
                return {
                    'fluent': False,
                    'fps': None,
                    'bitrate': None,
                    'error': 'stream_error'
                }

            # 6. 兜底判断：无严重错误即认为流畅
            return {
                'fluent': True,
                'fps': fps if fps > 0 else None,
                'bitrate': bitrate if bitrate > 0 else None,
                'error': None
            }

        except Exception as e:
            return {
                'fluent': False,
                'fps': None,
                'bitrate': None,
                'error': f'unknown_error: {str(e)}'
            }

    def check(self, url: str) -> dict:
        """
        完整检测 URL（可用性和流畅度）

        Args:
            url: 检测 URL

        Returns:
            检测结果字典，包含：
            - available: 是否可用
            - fluent: 是否流畅
            - fps: 帧率
            - bitrate: 码率
            - error: 错误信息
        """
        # 基础可用性检测
        available = self.check_available(url)
        if not available:
            return {
                'available': False,
                'fluent': False,
                'fps': None,
                'bitrate': None,
                'error': 'not_available'
            }

        # 流畅度检测
        fluent_result = self.check_fluent(url)

        return {
            'available': True,
            'fluent': fluent_result['fluent'],
            'fps': fluent_result['fps'],
            'bitrate': fluent_result['bitrate'],
            'error': fluent_result['error']
        }

    def check_channel(self, channel_input: Union[str, Dict, 'Channel'], 
                     logger: Optional[logging.Logger] = None) -> Optional['Channel']:
        """
        检测单个频道（支持 URL、字典或 Channel 对象）
        
        Args:
            channel_input: URL 字符串、频道字典或 Channel 对象
            logger: 日志记录器（可选）
        
        Returns:
            通过检测的 Channel 对象，失败返回 None
        """
        # 延迟导入检查
        if Channel is None or CheckResult is None:
            raise ImportError("Channel 或 CheckResult 未导入，请检查 models.channel 模块")
        
        # 转换为 Channel 对象
        if isinstance(channel_input, str):
            channel = Channel(channel_name="Unknown", url=channel_input)
        elif isinstance(channel_input, dict):
            channel = Channel.from_dict(channel_input)
        elif isinstance(channel_input, Channel):
            channel = channel_input
        else:
            if logger:
                logger.warning(f"无效的频道输入类型：{type(channel_input)}")
            return None
        
        # 验证频道信息
        if not channel.is_valid():
            if logger:
                logger.warning(f"频道信息不完整：{channel.channel_name or 'Unknown'}")
            return None
        
        # 使用基础检测方法
        result = self.check(channel.url)
        
        # 转换为 CheckResult
        check_result = CheckResult.from_iptv_checker_result(result, channel)
        
        # 不可用
        if not check_result.available:
            if logger:
                logger.debug(f"[不可用] {channel.channel_name}: {check_result.error}")
            return None
        
        # 不流畅
        if not check_result.fluent:
            error_msg = check_result.error or 'unknown'
            
            # 根据错误类型调整日志级别
            if logger:
                if error_msg == 'stream_lag':
                    logger.debug(f"[卡顿] {channel.channel_name}: 检测到丢包或帧丢失")
                elif error_msg.startswith('fps_too_low'):
                    fps_str = f"{check_result.fps:.2f}" if check_result.fps else "N/A"
                    logger.debug(f"[帧率低] {channel.channel_name}: fps={fps_str}")
                elif error_msg.startswith('bitrate_too_low'):
                    bitrate_str = f"{check_result.bitrate}" if check_result.bitrate else "N/A"
                    logger.debug(f"[码率低] {channel.channel_name}: bitrate={bitrate_str}kbps")
                else:
                    logger.debug(f"[不流畅] {channel.channel_name}: {error_msg}")
            
            return None
        
        # 通过检测
        if logger:
            fps_str = f"{check_result.fps:.2f}" if check_result.fps else "N/A"
            bitrate_str = f"{check_result.bitrate}" if check_result.bitrate else "N/A"
            logger.debug(f"[通过] {channel.channel_name}: fps={fps_str}, bitrate={bitrate_str}kbps, quality={channel.quality}")
        
        return check_result.channel
    
    def check_channels(self, channels: List[Union[str, Dict, 'Channel']], 
                      logger: Optional[logging.Logger] = None,
                      max_workers: int = None,  # 优化：默认使用实例的 max_workers
                      progress_callback: Optional[Callable[[int, int, any], None]] = None) -> List['Channel']:
        """
        批量检测频道（带并发和进度可视化）
        
        Args:
            channels: 频道列表（URL 字符串、字典或 Channel 对象）
            logger: 日志记录器（可选）
            max_workers: 最大并发数（默认使用实例的 max_workers 属性）
            progress_callback: 进度回调函数 callback(current, total, result)
        
        Returns:
            通过检测的 Channel 对象列表
        """
        # 使用实例的默认并发数
        if max_workers is None:
            max_workers = self.max_workers
        # 检查 ffmpeg 可用性
        if not self.is_ffmpeg_available():
            if logger:
                logger.warning("ffmpeg 未安装，跳过频道有效性检测")
            # 尝试转换为 Channel 对象返回
            if Channel:
                return [ch if isinstance(ch, Channel) else Channel.from_dict(ch) if isinstance(ch, dict) else Channel("Unknown", ch) for ch in channels]
            return list(channels)
        
        if logger:
            logger.info(f"开始检测频道有效性，共 {len(channels)} 个")
        
        # 记录开始时间
        start_time = time.time()
        
        valid_channels = []
        
        # 使用线程池并发检测
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.check_channel, ch, logger): ch for ch in channels}
            
            for idx, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    if result:
                        valid_channels.append(result)
                except Exception as e:
                    if logger:
                        logger.error(f"检测频道失败：{e}")
                
                # 调用进度回调
                if progress_callback:
                    progress_callback(idx, len(channels), valid_channels)
                
                # 定期输出进度（优化：减少日志输出频率，每 50 个输出一次）
                if logger and idx % 50 == 0:
                    logger.info(f"检测进度：{idx}/{len(channels)}，已通过 {len(valid_channels)} 个")
        
        # 计算总耗时
        elapsed_time = time.time() - start_time
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        
        if logger:
            if hours > 0:
                logger.info(f"频道检测完成，有效：{len(valid_channels)}/{len(channels)}，耗时：{hours}小时 {minutes}分钟 {seconds}秒")
            elif minutes > 0:
                logger.info(f"频道检测完成，有效：{len(valid_channels)}/{len(channels)}，耗时：{minutes}分钟 {seconds}秒")
            else:
                logger.info(f"频道检测完成，有效：{len(valid_channels)}/{len(channels)}，耗时：{seconds}秒")
        
        return valid_channels


# 便捷函数
def check_channel(url: Union[str, Dict]) -> Dict:
    """
    便捷函数：检测单个频道
    
    Args:
        url: 播放 URL 或频道字典
    
    Returns:
        检测结果字典
    """
    checker = IPTVChecker()
    return checker.check_channel(url)


def check_channels(channels: List[Union[str, Dict]], 
                  progress_callback=None) -> List[Dict]:
    """
    便捷函数：批量检测频道
    
    Args:
        channels: 频道列表
        progress_callback: 进度回调函数
    
    Returns:
        检测结果列表
    """
    checker = IPTVChecker()
    return checker.check_channels(channels, progress_callback)



if __name__ == "__main__":
    # 测试示例
    test_url = "https://live.ottiptv.cc/mcp/cctv5.m3u8?userid=7755950497&sign=21c19c68084634070c8135e8e586757c920a4eae0cafef40255c1768a60d633fa90acb1b5cd4def1bdbf13bdd4b48813a2bc84e9076a11b9b9e9ae3f6cdfff025c12201dc1579aeb9678817a4b&auth_token=17b0d6712a2beb7e9bfea802dc9d33a3"

    print(f"测试 URL: {test_url}")
    print("-" * 60)

    checker = IPTVChecker()
    result = checker.check_channel(test_url)

    print(f"可用性：{'✓' if result['available'] else '✗'}")
    print(f"流畅度：{'✓' if result['fluent'] else '✗'}")
    print(f"帧  率：{result['fps']:.2f} fps" if result['fps'] else "帧  率：未检测到")
    print(f"码  率：{result['bitrate']} kbps" if result['bitrate'] else "码  率：未检测到")
    print(f"错  误：{result['error']}" if result['error'] else "错  误：无")