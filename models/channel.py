"""
IPTV 频道数据模型

定义频道相关的数据类和枚举类型
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ChannelQuality(Enum):
    """频道质量等级"""
    HD = "hd"      # 高清：fps >= 24, bitrate >= 2000
    SD = "sd"      # 标清：fps >= 20, bitrate >= 1000
    LOW = "low"    # 低清：其他


@dataclass
class Channel:
    """
    IPTV 频道数据类
    
    Attributes:
        channel_name: 频道名称
        url: 播放地址
        tvg_id: TVG ID
        tvg_name: TVG 名称
        tvg_logo: 频道图标
        group_title: 分组名称
        quality: 频道质量（检测后填充）
        fps: 帧率（检测后填充）
        bitrate: 码率（检测后填充）
    """
    channel_name: str
    url: str
    tvg_id: str = ""
    tvg_name: str = ""
    tvg_logo: str = ""
    group_title: str = ""
    quality: str = ChannelQuality.LOW.value
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'channel_name': self.channel_name,
            'url': self.url,
            'tvg_id': self.tvg_id,
            'tvg_name': self.tvg_name,
            'tvg_logo': self.tvg_logo,
            'group_title': self.group_title,
            'type': self.type,
            'quality': self.quality,
            'fps': self.fps,
            'bitrate': self.bitrate
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Channel':
        """从字典创建"""
        return cls(
            channel_name=data.get('channel_name', ''),
            url=data.get('url', ''),
            tvg_id=data.get('tvg_id', ''),
            tvg_name=data.get('tvg_name', ''),
            tvg_logo=data.get('tvg_logo', ''),
            group_title=data.get('group_title', ''),
            type=data.get('type', 'video'),
            quality=data.get('quality', 'unknown'),
            fps=data.get('fps'),
            bitrate=data.get('bitrate')
        )
    
    def is_valid(self) -> bool:
        """检查频道基本信息是否有效"""
        return bool(self.channel_name and self.url)
    
    def update_quality(self, fps: Optional[float] = None, bitrate: Optional[int] = None):
        """
        更新频道质量信息
        
        Args:
            fps: 帧率
            bitrate: 码率 (kbps)
        """
        if fps is not None:
            self.fps = fps
        if bitrate is not None:
            self.bitrate = bitrate
        
        # 根据帧率和码率判断质量等级
        if self.type == "audio":
            # 音频频道：仅根据码率判断
            if bitrate and bitrate >= 128:
                self.quality = ChannelQuality.HD.value
            elif bitrate and bitrate >= 64:
                self.quality = ChannelQuality.SD.value
            else:
                self.quality = ChannelQuality.LOW.value
        else:
            # 视频频道：综合帧率和码率判断
            # 优先使用码率判断（更准确），其次使用帧率判断（兜底）
            has_bitrate = bitrate and bitrate > 200  # 排除 FFmpeg 输出流的虚假码率 200kbps
            has_fps = fps and fps > 0
            
            if has_bitrate:
                # 有真实码率信息：优先使用码率判断
                if bitrate >= 2000:
                    self.quality = ChannelQuality.HD.value
                elif bitrate >= 1000:
                    self.quality = ChannelQuality.SD.value
                else:
                    self.quality = ChannelQuality.LOW.value
            elif has_fps:
                # 无真实码率信息：使用帧率判断（兜底策略）
                if fps >= 24:
                    # 帧率 >= 24 通常是高清内容（如电视广播 25/30fps）
                    self.quality = ChannelQuality.HD.value
                elif fps >= 20:
                    # 帧率 >= 20 可接受为标清
                    self.quality = ChannelQuality.SD.value
                else:
                    self.quality = ChannelQuality.LOW.value
            else:
                # 既无码率也无帧率：标记为低清
                self.quality = ChannelQuality.LOW.value
    
    def __str__(self) -> str:
        """字符串表示"""
        quality_str = self.quality.upper() if self.quality else "N/A"
        fps_str = f"{self.fps:.2f}fps" if self.fps else "N/A"
        bitrate_str = f"{self.bitrate}kbps" if self.bitrate else "N/A"
        return f"{self.channel_name} [{quality_str}] fps={fps_str}, bitrate={bitrate_str}"


@dataclass
class CheckResult:
    """
    频道检测结果
    
    Attributes:
        success: 是否通过检测
        available: 是否可用
        fluent: 是否流畅
        fps: 帧率
        bitrate: 码率
        error: 错误信息
        channel: 频道对象（如果通过检测）
    """
    success: bool = False
    available: bool = False
    fluent: bool = False
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    error: Optional[str] = None
    channel: Optional[Channel] = None
    
    @classmethod
    def from_iptv_checker_result(cls, result: dict, channel: Optional[Channel] = None) -> 'CheckResult':
        """
        从 IPTVChecker 的检测结果创建
        
        Args:
            result: IPTVChecker.check() 返回的字典
            channel: 频道对象
        
        Returns:
            CheckResult 实例
        """
        success = result.get('available', False) and result.get('fluent', False)
        
        check_result = cls(
            success=success,
            available=result.get('available', False),
            fluent=result.get('fluent', False),
            fps=result.get('fps'),
            bitrate=result.get('bitrate'),
            error=result.get('error'),
            channel=channel
        )
        
        # 如果通过检测，更新频道质量信息
        if success and channel:
            channel.update_quality(
                fps=result.get('fps'),
                bitrate=result.get('bitrate')
            )
            check_result.channel = channel
        
        return check_result
