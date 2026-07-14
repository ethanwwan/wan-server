import os
import sys

iptv_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(iptv_root)
for p in [project_root, iptv_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from core.aggregator import fetch_playlist

__all__ = ['fetch_playlist']


if __name__ == "__main__":
    fetch_playlist()
