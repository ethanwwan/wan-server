"""
统一文件路径解析

API 文件中常需要构造 output 目录下的文件路径，本模块统一封装。

注意：路径计算基于 constants.get_project_root()（与 scheduler_base 一致），
不依赖 `__file__` 相对位置（utils 模块位置变化不影响计算结果）。
"""
import os
from .constants import get_project_root


def get_output_path(sub_dir: str) -> str:
    """
    构造 output 目录下的子目录路径

    Args:
        sub_dir: output 下的子目录（如 'proxy'、'iptv'、'tvbox'）
    """
    return os.path.join(get_project_root(), 'server', 'output', sub_dir)


def get_output_file(sub_dir: str, file_name: str) -> str:
    """
    构造 output 目录下的文件完整路径

    Args:
        sub_dir: output 下的子目录
        file_name: 文件名
    """
    return os.path.join(get_output_path(sub_dir), file_name)