"""
IPTV 配置模块

集中管理所有 IPTV 相关配置，便于维护和扩展
"""

import os
from dataclasses import dataclass
from typing import Tuple, Dict, List


@dataclass(frozen=True)
class IPTVConfig:
    """IPTV 检测核心配置"""
    
    # 并发配置
    DEFAULT_WORKERS: int = 10
    MAX_WORKERS: int = 100
    BATCH_SIZE: int = 300
    
    # 超时配置
    HTTP_TIMEOUT: int = 20
    FFMPEG_TIMEOUT: int = 5
    RETRY_TIMEOUT_BASE: float = 0.1
    
    # 缓存配置
    CACHE_EXPIRE_PERMANENT: int = 24 * 3600  # 确定性错误缓存 24 小时
    CACHE_EXPIRE_TEMPORARY: int = 3600        # 临时性错误缓存 1 小时
    CACHE_MAX_AGE: int = 7 * 24 * 3600        # 缓存最大保留时间 7 天
    
    # 视频质量配置
    MIN_FPS: int = 20
    MIN_BITRATE: int = 1000  # kbps
    
    # 重试配置
    MAX_RETRIES: int = 2
    
    # 分类配置
    GROUP_MAPPING: Dict[str, List[str]] = None
    CHANNEL_MAPPING: Dict[str, List[str]] = None
    
    @classmethod
    def build(cls) -> 'IPTVConfig':
        """构建完整配置"""
        return cls(
            GROUP_MAPPING={
                '央视频道': ['央视'],
                '卫视频道': ['卫视'],
                '地方频道': ['地方', '浙江频道', '江苏频道', '广东频道', '湖南频道', '湖北频道', 
                           '四川频道', '河南频道', '河北频道', '山东频道', '山西频道', '陕西频道', 
                           '安徽频道', '福建频道', '江西频道', '辽宁频道', '吉林频道', '黑龙江频道', 
                           '北京频道', '上海频道', '天津频道', '重庆频道', '云南频道', '贵州频道', 
                           '广西频道', '海南频道', '甘肃频道', '青海频道', '内蒙古频道', '宁夏频道', 
                           '新疆频道', '西藏频道'],
                '电影电视': ['电影', '埋堆堆', '电视剧', '剧场', '影视'],
                '体育赛事': ['体育', '咪咕赛事'],
                '少儿教育': ['少儿', '动漫', '儿童', '动画'],
                '综艺娱乐': ['综艺', '音乐'],
                '纪录纪实': ['纪录', '直播中国', '纪实'],
                '国际全球': ['国际', '全球', '外语'],
                '港澳台': ['港·澳·台', '港澳', '港台'],
                '咪视界': ['咪视界', '咪视通'],
                'NewTV': ['NewTV'],
                'iHOT': ['IHOT'],
                'iPanda': ['ipanda']
            },
            CHANNEL_MAPPING={
                '央视频道': ['CCTV', 'CGTN'],
                '卫视频道': ['湖南卫视', '江苏卫视', '浙江卫视', '东方卫视', '北京卫视', '广东卫视', 
                           '安徽卫视', '山东卫视', '河南卫视', '河北卫视', '湖北卫视', '四川卫视', 
                           '重庆卫视', '天津卫视', '江西卫视', '云南卫视', '贵州卫视', '广西卫视', '苏州4K'],
                '地方频道': ['重庆', '天津', '山东', '山西', '陕西', '福建', '安徽', '贵州', '云南', 
                           '广西', '海南', '黑龙江', '吉林', '辽宁', '内蒙古', '宁夏', '新疆', '青海', 
                           '甘肃', '西藏', '地方', '广州', '佛山', '江门', '汕头', '深圳', '珠海', '东莞', 
                           '中山', '惠州', '肇庆', '清远', '韶关', '河源', '梅州', '汕尾', '揭阳', '阳江', 
                           '茂名', '湛江', '潮州', '云浮', '南宁', '南京', '宁波', '杭州', '余杭', '上虞', 
                           '湖州', '松阳', '庆元', '民视', '余姚', '开化', '南国', '邢台', '绍兴', '嵊州', 
                           '新昌', '福州', '萧山', '钱江', '财经', '新闻综合'],
                '电影电视': ['电影'],
                '体育赛事': ['体育', '足球'],
                '少儿教育': ['少儿', '动画', '卡通', '动漫'],
                '综艺娱乐': ['综艺', '娱乐', '音乐'],
                '国际全球': ['国际', 'UK', '美亚'],
                '纪录纪实': ['纪录', '人文', '历史', '地理', '自然', '生物', '纪实', '睛彩'],
                '港澳台': ['台湾', 'Taiwan', 'TVB', 'ATV', '公视', '华视', '台视', '中视', '东森', '中天', 
                          '凤凰', '澳亚', 'CHANNEL', 'CH5', 'CH8', '频道', 'VIUTV', 'RTHK', '明珠台', 
                          'HOY', 'ASTRO', '欢喜台', 'AOD', 'AEC', 'QJ', '港·澳·台', '港澳', '港台'],
                '咪视界': ['咪视界', '咪视通'],
                'NewTV': ['NewTV'],
                'iHOT': ['IHOT'],
                'iPanda': ['ipanda']
            }
        )


@dataclass(frozen=True)
class ErrorPatterns:
    """错误模式定义（集中管理）"""
    
    # 临时性错误（需要重试）
    TEMPORARY_ERRORS: Tuple[str, ...] = (
        'http_timeout',
        'connection_error',
        'connection_timeout',
        'connection_refused',
        'connection_reset',
        'ffmpeg_timeout',
        'network_error',
        'reset_by_peer',
        'http_error',
        'server_error'
    )
    
    # 确定性错误（不需要重试）
    PERMANENT_ERRORS: Tuple[str, ...] = (
        'invalid_url',
        'status_404',
        'status_403',
        'ffmpeg_error_not_found_404',
        'ffmpeg_error_forbidden_403',
        'ffmpeg_error_file_not_found',
        'ffmpeg_error_protocol_not_found',
        '_404',
        '_403',
        '_not_found',
        '_protocol_not_found'
    )


def get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_cache_path() -> str:
    """获取缓存文件路径"""
    return os.path.join(get_project_root(), 'output', 'iptv', 'cache', 'fail_cache.json')


def get_output_dir() -> str:
    """获取输出目录"""
    return os.path.join(get_project_root(), 'output', 'iptv')


def get_input_file_path(filename: str) -> str:
    """获取输入文件路径"""
    return os.path.join(get_project_root(), 'input', filename)