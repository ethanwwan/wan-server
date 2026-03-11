from utils.iptv_utils import classify_channels

# 测试数据
test_channels = [
    {'channel_name': '湖南卫视', 'url': 'http://example.com', 'group_title': '卫视'},
    {'channel_name': 'CCTV1', 'url': 'http://example.com', 'group_title': '央视'},
    {'channel_name': '北京卫视', 'url': 'http://example.com', 'group_title': '卫视'},
    {'channel_name': 'CCTV1综合', 'url': 'http://example.com', 'group_title': '央视'},
    {'channel_name': 'CCTV2财经', 'url': 'http://example.com', 'group_title': '央视'}
]

try:
    print('Testing classify_channels...')
    result = classify_channels(test_channels)
    print('Classification successful:', len(result), 'channels')
    for channel in result:
        print(f"Channel: {channel['channel_name']}, Group: {channel['group_title']}")
    print('Test passed!')
except Exception as e:
    print('Error:', type(e).__name__, ':', str(e))
    import traceback
    traceback.print_exc()
