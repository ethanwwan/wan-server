



def sort_channels_by_url_priority(channels):
    """
    按URL优先级排序频道
    
    排序规则：
    1. 第一遍排序：按照group-title字段中的，央视，卫视，地方，其他分类
    2. 第二遍排序：包含live.ottiptv.cc的URL优先。包含mgtv.ottiptv.cc的URL次之。其他URL最后。
    3. 相同优先级按URL字母顺序排序
    
    Args:
        channels: 频道信息列表
    
    返回:
        list: 排序后的频道信息列表
    """
    def get_sort_key(channel):
        """
        生成排序键
        
        Args:
            channel: 频道信息字典
        
        返回:
            tuple: 排序键元组
        """
        # 1. 按group-title分类排序
        group_title = channel.get('group_title', '').strip()
        group_priority = {
            '央视': 0,
            '卫视': 1,
            '地方': 2
        }
        # 默认优先级为3（其他分类）
        group_score = group_priority.get(group_title, 3)
        
        # 2. 按域名优先级排序
        url = channel.get('url', '')
        domain_priorities = ['live.ottiptv.cc', 'mgtv.ottiptv.cc']
        domain_score = len(domain_priorities)
        for i, domain in enumerate(domain_priorities):
            if domain in url:
                domain_score = i
                break
 
        return (group_score, domain_score)
    
    return sorted(channels, key=get_sort_key)

def assemble_m3u_config(channels):
    """
    重新组装成M3U格式配置
    
    Args:
        channels: 频道信息列表
    
    返回:
        str: M3U格式配置内容
    """
    config = "#EXTM3U x-tvg-url=\"https://11.112114.xyz/pp.xml\"\n"
    
    for channel in channels:
        # 构建EXTINF行
        extinf_parts = ["#EXTINF:-1"]
        
        if channel['tvg_name']:
            extinf_parts.append(f"tvg-name=\"{channel['tvg_name']}\"")
        
        if channel['tvg_logo']:
            extinf_parts.append(f"tvg-logo=\"{channel['tvg_logo']}\"")
        
        if channel['group_title']:
            extinf_parts.append(f"group-title=\"{channel['group_title']}\"")
        
        extinf_line = " ".join(extinf_parts) + f",{channel['name']}"
        config += f"{extinf_line}\n"
        config += f"{channel['url']}\n"
    
    return config

