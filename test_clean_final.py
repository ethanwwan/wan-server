from utils.iptv_utils import _clean_channel_name

# 测试数据
test_names = [
    'CCTV-1',
    'CCTV1',
    'CCTV1综合',
    'CCTV-2',
    'CCTV2',
    'CCTV2财经',
    'CCTV-3'
]

print('Testing _clean_channel_name...')
for name in test_names:
    cleaned = _clean_channel_name(name)
    print(f'Original: {name:10} → Cleaned: {cleaned:10}')
