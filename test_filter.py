from utils.iptv_utils import classify_channels

# 测试地方频道过滤
test_channels = [
    {'channel_name': '北京卫视', 'url': 'http://example.com', 'group_title': '地方'},
    {'channel_name': '6', 'url': 'http://example.com', 'group_title': '地方'},
    {'channel_name': 'AYXTV', 'url': 'http://example.com', 'group_title': '地方'},
    {'channel_name': 'PVA', 'url': 'http://example.com', 'group_title': '地方'},
    {'channel_name': 'XXTV', 'url': 'http://example.com', 'group_title': '地方'},
    {'channel_name': '上海卫视', 'url': 'http://example.com', 'group_title': '地方'},
]

result = classify_channels(test_channels)
print('测试结果:')
for ch in result:
    print(f"  Channel: {ch['channel_name']}, Group: {ch['group_title']}")
