"""
缓存管理器模块

提供统一的缓存管理接口，支持单例模式和批量操作
"""

import json
import os
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

from .iptv_config import get_cache_path, IPTVConfig, ErrorPatterns

logger = logging.getLogger("CACHE_MANAGER")


class CacheManager:
    """缓存管理器（单例模式）"""
    
    _instance: Optional['CacheManager'] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._cache: Dict[str, dict] = {}
        self._config = IPTVConfig.build()
        self._error_patterns = ErrorPatterns()
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
            
            # 清理过期记录
            self._clean_expired()
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            logger.info(f"[缓存策略] 缓存已写入磁盘，共 {len(self._cache)} 条记录")
        except Exception as e:
            logger.error(f"[缓存策略] 保存缓存到磁盘失败: {e}")
    
    def _clean_expired(self):
        """清理过期记录"""
        now = datetime.now()
        self._cache = {
            url: record 
            for url, record in self._cache.items()
            if 'last_fail_time' in record and 
               (now - datetime.fromisoformat(record['last_fail_time'])).total_seconds() < self._config.CACHE_MAX_AGE
        }
    
    def _is_permanent_error(self, error: str) -> bool:
        """判断是否为确定性错误"""
        return any(pattern in error for pattern in self._error_patterns.PERMANENT_ERRORS)
    
    def get_cache(self) -> Dict[str, dict]:
        """获取缓存字典（只读）"""
        return self._cache
    
    def is_expired(self, url: str) -> bool:
        """检查 URL 是否在缓存中且未过期"""
        if url not in self._cache:
            return True
        
        record = self._cache[url]
        fail_time = datetime.fromisoformat(record['last_fail_time'])
        skip_seconds = self._config.CACHE_EXPIRE_PERMANENT if record.get('is_permanent', False) else self._config.CACHE_EXPIRE_TEMPORARY
        
        return (datetime.now() - fail_time).total_seconds() >= skip_seconds
    
    def batch_update(self, successes: Tuple[str, ...], failures: Tuple[Tuple[str, str], ...]):
        """
        批量更新缓存
        
        Args:
            successes: 成功的 URL 列表（需要从缓存移除）
            failures: 失败的 (URL, error) 元组列表（需要加入缓存）
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
        for url, error in failures:
            if url not in self._cache:
                self._cache[url] = {
                    'fail_count': 0,
                    'last_fail_time': '',
                    'fail_type': 'unknown',
                    'is_permanent': False
                }
            
            record = self._cache[url]
            record['fail_count'] += 1
            record['last_fail_time'] = datetime.now().isoformat()
            record['fail_type'] = error
            record['is_permanent'] = self._is_permanent_error(error)
            added_count += 1
        
        if added_count > 0:
            logger.info(f"[缓存策略] 批量更新 {added_count} 条失败记录")
    
    def clear_all(self):
        """清空所有缓存（周日清理时使用）"""
        self._cache = {}
        logger.info("[缓存策略] 已清空所有缓存")
    
    def clear_expired(self):
        """仅清理过期记录"""
        old_count = len(self._cache)
        self._clean_expired()
        removed_count = old_count - len(self._cache)
        if removed_count > 0:
            logger.info(f"[缓存策略] 清理了 {removed_count} 条过期记录")


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例"""
    return CacheManager()