from utils.iptv_utils import _clean_channel_name

# 测试数据
name = 'CCTV1综合'
cleaned = _clean_channel_name(name)
print(f'Original: {name}')
print(f'Cleaned: {cleaned}')
