import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

iptv_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(iptv_root)
for p in [project_root, iptv_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from core.iptv_utils import parse_url, classify_channels
from core.iptv_checker import IPTVChecker

INPUT_FILE = os.path.join(iptv_root, 'input', 'iptv_urls.txt')

checker = IPTVChecker(
    fps_min=0,
    bitrate_min=0,
    max_workers=100
)


def fetch_and_parse(url: str) -> list[dict]:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        channels = parse_url(url, r.text)
        return classify_channels(channels, keep_unmatched=True)
    except Exception as e:
        print(f"  ⚠️  获取/解析失败: {e}")
        return []


def stats():
    with open(INPUT_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"共 {len(urls)} 个源\n")
    print(f"{'#':<4} {'URL':<75} {'总数':<6} {'成功':<6} {'失败':<6} {'成功率':<8} {'失败率':<8}")
    print("-" * 115)

    all_results = []

    for idx, url in enumerate(urls, 1):
        short = url if len(url) <= 73 else url[:70] + "..."
        print(f"{idx:<4} {short:<75}", end="", flush=True)

        channels = fetch_and_parse(url)
        if not channels:
            print(f"{'0':<6} {'0':<6} {'0':<6} {'0%':<8} {'0%':<8}")
            continue

        urls_list = [(ch.get('channel_name', ''), ch.get('url', '')) for ch in channels]
        total = len(urls_list)

        ch_map = {ch['url']: ch for ch in channels}
        success = []
        fail = 0
        with ThreadPoolExecutor(max_workers=min(100, total or 1)) as executor:
            fut_map = {executor.submit(checker.check, u): u for _, u in urls_list}
            for fut in as_completed(fut_map):
                u = fut_map[fut]
                try:
                    result = fut.result()
                    if result.get('available'):
                        success.append(ch_map.get(u, {'channel_name': '?', 'url': u, 'group_title': '其他'}))
                    else:
                        fail += 1
                except Exception:
                    fail += 1

        ok = len(success)
        ng = total - ok
        pct_ok = ok / total * 100 if total else 0
        pct_ng = ng / total * 100 if total else 0
        print(f"{total:<6} {ok:<6} {ng:<6} {pct_ok:<7.1f}% {pct_ng:<7.1f}%")

        all_results.append((url, success))

    print("\n" + "=" * 115)

    for url, success in all_results:
        if not success:
            continue
        classified = classify_channels(success, keep_unmatched=True)
        groups = Counter(ch.get('group_title', '其他') for ch in classified)
        top5 = groups.most_common(5)

        print(f"\n📺 {url}")
        print(f"  成功频道: {len(success)} 个")
        print(f"  TOP5 GROUP:")
        for g, cnt in top5:
            pct = cnt / len(success) * 100
            print(f"    {g:<20} {cnt:>4}  ({pct:.1f}%)")


if __name__ == "__main__":
    stats()
