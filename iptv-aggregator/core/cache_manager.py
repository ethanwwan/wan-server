"""
缓存管理器模块

提供统一的缓存管理接口，支持单例模式和批量操作
"""

import json
import os
from typing import Dict, Optional
import logging

from .iptv_config import get_cache_path

logger = logging.getLogger("CACHE_MANAGER")


class CacheManager:
    """缓存管理器（单例模式）- 简化版"""
    
    _instance: Optional['CacheManager'] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._cache: Dict[str, int] = {}  # 简化结构：url -> 1
        self._load_cache()
        self._initialized = True
    
    def _load_cache(self):
        """从磁盘加载缓存"""
        try:
            cache_path = get_cache_path()
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            logger.info(f"[缓存策略] 加载失败缓存完成，共 {len(self._cache)} 条失败记录")
        except Exception as e:
            logger.error(f"[缓存策略] 加载失败缓存失败: {e}")
            self._cache = {}
    
    def save_to_disk(self):
        """将缓存保存到磁盘"""
        try:
            cache_path = get_cache_path()
            cache_dir = os.path.dirname(cache_path)
            os.makedirs(cache_dir, exist_ok=True)
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            logger.info(f"[缓存策略] 缓存已写入磁盘，共 {len(self._cache)} 条记录")
        except Exception as e:
            logger.error(f"[缓存策略] 保存缓存到磁盘失败: {e}")
    
    def get_cache(self) -> Dict[str, int]:
        """获取缓存字典（只读）"""
        return self._cache
    
    def is_in_cache(self, url: str) -> bool:
        """检查 URL 是否在缓存中"""
        return url in self._cache
    
    def batch_update(self, successes: tuple, failures: tuple):
        """
        批量更新缓存
        
        Args:
            successes: 成功的 URL 列表（需要从缓存移除）
            failures: 失败的 URL 列表（需要加入缓存）
        """
        # 移除成功的 URL
        removed_count = 0
        for url in successes:
            if url in self._cache:
                del self._cache[url]
                removed_count += 1
        if removed_count > 0:
            logger.info(f"[缓存策略] 批量移除 {removed_count} 条成功记录")
        
        # 添加失败的 URL
        added_count = 0
        for url in failures:
            if url not in self._cache:
                self._cache[url] = 1
                added_count += 1
        
        if added_count > 0:
            logger.info(f"[缓存策略] 批量添加 {added_count} 条失败记录")
    
    def clear_all(self):
        """清空所有缓存（周日清理时使用）"""
        self._cache = {}
        logger.info("[缓存策略] 已清空所有缓存")
    
    def reload(self):
        """重新加载缓存（周日清空后调用）"""
        self._load_cache()


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例"""
    return CacheManager()
