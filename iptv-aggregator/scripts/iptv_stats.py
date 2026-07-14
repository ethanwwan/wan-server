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

from iptv_utils import parse_url, classify_channels
from iptv_checker import IPTVChecker

INPUT_FILE = os.path.join(iptv_root, 'input', 'iptv_urls.txt')

checker = IPTVChecker(max_workers=100)


def fetch_and_parse(url: str) -> list[dict]:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return classify_channels(parse_url(url, r.text), keep_unmatched=False)
    except Exception as e:
        print(f"  ! 获取/解析失败: {e}")
        return []


def stats():
    with open(INPUT_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    threshold = f"阈值: {checker.width_min}x{checker.height_min} / {checker.fps_min}fps / {checker.bitrate_min}kbps"
    print(f"共 {len(urls)} 个源 ({threshold})\n")
    print(f"{'#':<4} {'URL':<72} {'总数':>5} {'可用':>5} {'流畅':>5} {'失败':>5} {'可用率':>6} {'流畅率':>6}")
    print("-" * 115)

    all_data = []

    for idx, url in enumerate(urls, 1):
        short = url if len(url) <= 70 else url[:67] + "..."
        print(f"{idx:<4} {short:<72}", end="", flush=True)

        channels = fetch_and_parse(url)
        if not channels:
            print(f"{'0':>5} {'0':>5} {'0':>5} {'0':>5} {'0%':>6} {'0%':>6}")
            all_data.append((url, 0, 0, 0, []))
            continue

        total = len(channels)
        ok = fail = fluent = 0
        fluent_channels = []

        with ThreadPoolExecutor(max_workers=min(100, total or 1)) as executor:
            futs = {executor.submit(checker.check, ch['url']): ch for ch in channels}
            for fut in as_completed(futs):
                ch = futs[fut]
                try:
                    r = fut.result()
                    if r.get('fluent'):
                        fluent += 1
                        ok += 1
                        fluent_channels.append(ch)
                    elif r.get('available'):
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1

        ng = total - ok
        pa = ok / total * 100 if total else 0
        pf = fluent / total * 100 if total else 0
        print(f"{total:>5} {ok:>5} {fluent:>5} {ng:>5} {pa:>5.1f}% {pf:>5.1f}%")

        all_data.append((url, total, ok, fluent, fluent_channels))

    print()
    print("-" * 115)

    total_sum = sum(d[1] for d in all_data)
    avail_sum = sum(d[2] for d in all_data)
    fluent_sum = sum(d[3] for d in all_data)
    fail_sum = total_sum - avail_sum
    pa = avail_sum / total_sum * 100 if total_sum else 0
    pf = fluent_sum / total_sum * 100 if total_sum else 0
    print(f"{'':<4} {'合计':<72} {total_sum:>5} {avail_sum:>5} {fluent_sum:>5} {fail_sum:>5} {pa:>5.1f}% {pf:>5.1f}%")
    if avail_sum:
        print(f"{'':<4} {'流畅率(占原始)':<72} {pf:>5.1f}%")
        print(f"{'':<4} {'流畅率(占可用)':<72} {fluent_sum/avail_sum*100:>5.1f}%")
    print()

    for idx, (url, _, _, _, fluent_channels) in enumerate(all_data, 1):
        if not fluent_channels:
            continue
        groups = Counter(ch.get('group_title', '其他') for ch in fluent_channels)
        top5 = groups.most_common(5)
        print(f"#{idx} {url}")
        print(f"  流畅频道: {len(fluent_channels)} 个")
        print(f"  TOP5 GROUP:")
        for g, cnt in top5:
            print(f"    {g:<20} {cnt:>4}  ({cnt/len(fluent_channels)*100:.1f}%)")


if __name__ == "__main__":
    stats()
