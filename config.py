#!/usr/bin/env python3
"""
配置管理模块
从 config.yaml 文件中读取配置
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from importlib import import_module


class SchedulerJobConfig:
    """
    调度任务配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    @property
    def id(self) -> str:
        return self._config.get('id', '')
    
    @property
    def name(self) -> str:
        return self._config.get('name', '')
    
    @property
    def func(self) -> str:
        return self._config.get('func', '')
    
    @property
    def hour(self) -> int:
        return self._config.get('hour', 0)
    
    @property
    def minute(self) -> int:
        return self._config.get('minute', 0)
    
    def get_func(self):
        """获取可执行的函数对象"""
        if not self.func:
            return None
        try:
            module_path, func_name = self.func.rsplit('.', 1)
            module = import_module(module_path)
            return getattr(module, func_name)
        except Exception:
            return None


class SchedulerConfig:
    """
    调度任务配置类
    """
    def __init__(self, config: List[Dict[str, Any]]):
        self._config = config
    
    def __iter__(self):
        for item in self._config:
            yield SchedulerJobConfig(item)
    
    def __len__(self):
        return len(self._config)
    
    def __getitem__(self, index):
        return SchedulerJobConfig(self._config[index])


class AppConfig:
    """
    应用配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)
    
    @property
    def env(self) -> str:
        return self._config.get('env', 'dev')
    
    @property
    def debug(self) -> bool:
        return self._config.get('debug', False)


class ServerConfig:
    """
    服务器配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    @property
    def host(self) -> str:
        return self._config.get('host', '0.0.0.0')
    
    @property
    def port(self) -> int:
        return self._config.get('port', 8016)


class SingboxConfig:
    """
    Singbox 配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    @property
    def url(self) -> str:
        return self._config.get('url', '')
    
    @property
    def version(self) -> str:
        return self._config.get('version', '')
    
    @property
    def old_version(self) -> str:
        return self._config.get('old_version', '')
    
    @property
    def global_ruleset_url(self) -> str:
        return self._config.get('global_ruleset_url', '')


class TvboxConfig:
    """
    TVBox 配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    @property
    def url(self) -> str:
        return self._config.get('url', '')


class IptvConfig:
    """
    IPTV 配置类
    """
    def __init__(self, config: Dict[str, Any]):
        self._config = config
    
    @property
    def migu_url(self) -> str:
        return self._config.get('migu_url', '')
    
    @property
    def ott_url(self) -> str:
        return self._config.get('ott_url', '')
    
    @property
    def playlist_url(self) -> str:
        return self._config.get('playlist_url', '')


class Config:
    """
    配置管理类
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置类
        
        Args:
            config_path: 配置文件路径，默认为项目根目录下的 input/config.yaml
        """
        if config_path is None:
            self.project_root = os.path.dirname(os.path.abspath(__file__))
            self.config_path = os.path.join(self.project_root, 'input', 'config.yaml')
        else:
            self.config_path = config_path
        
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> 'Config':
        """
        加载配置文件
        
        Returns:
            Config: 返回自身以便链式调用
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在：{self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        return self
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        return self._config.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """
        获取完整配置字典
        
        Returns:
            Dict[str, Any]: 完整配置
        """
        return self._config.copy()
    
    @property
    def app(self) -> AppConfig:
        """
        获取应用配置
        
        Returns:
            AppConfig: 应用配置
        """
        return AppConfig(self.get('app', {}))
    
    @property
    def server(self) -> ServerConfig:
        """
        获取服务器配置
        
        Returns:
            ServerConfig: 服务器配置
        """
        return ServerConfig(self.get('server', {}))
    
    @property
    def singbox(self) -> SingboxConfig:
        """
        获取 Singbox 配置
        
        Returns:
            SingboxConfig: Singbox 配置
        """
        return SingboxConfig(self.get('singbox', {}))
    
    @property
    def tvbox(self) -> TvboxConfig:
        """
        获取 TVBox 配置
        
        Returns:
            TvboxConfig: TVBox 配置
        """
        return TvboxConfig(self.get('tvbox', {}))
    
    @property
    def iptv(self) -> IptvConfig:
        """
        获取 IPTV 配置
        
        Returns:
            IptvConfig: IPTV 配置
        """
        return IptvConfig(self.get('iptv', {}))
    
    @property
    def scheduler(self) -> SchedulerConfig:
        """
        获取调度任务配置
        
        Returns:
            SchedulerConfig: 调度任务配置
        """
        return SchedulerConfig(self.get('scheduler', []))


# 全局配置实例
_config_instance: Optional[Config] = None


def _get_config() -> Config:
    """
    获取全局配置实例（单例模式）
    
    Returns:
        Config: 配置实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


# 全局配置实例，可直接导入使用
CONFIG = _get_config()
