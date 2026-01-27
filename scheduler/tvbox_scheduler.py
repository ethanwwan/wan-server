import os
import json
import requests
import re
from datetime import datetime
import time

# TVBox配置目录
TVBOX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'tvbox')

TVBOX_URL = os.getenv("TVBOX_URL","https://www.iyouhun.com/tv/dc")
headers = {
    "User-Agent": "okhttp/3.12.12",
    "Accept": "application/json"
}  

# 确保目录存在
os.makedirs(TVBOX_DIR, exist_ok=True)

def tvbox_scheduler():
    """
    TVBox配置调度器
    
    - 请求 https://www.iyouhun.com/tv/dc 接口获取数据
    - 解析得到urls的数组
    - 遍历数组，拿到每个url并请求数据
    - 按url的格式，将数据保存到public/tvbox目录下
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 开始更新配置")
    
    try:
        # 请求主接口获取urls数组
    
        response = requests.get(TVBOX_URL, headers=headers, timeout=20)
        response.raise_for_status()
        
        data = response.json()
        if data is None or 'urls' not in data:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 主接口返回数据格式错误")
            return

        urls = data.get('urls', [])
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 成功获取 {len(urls)} 个配置URL")
        
        new_urls = []
        # 遍历urls数组
        for item in urls:

            item_url = ""
            try:

                new_item = item.copy()

                # 处理不同格式的数据
                item_url = item.get('url', '')
                name = item.get('name', '')
                #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 处理URL: {name} - {item_url}")
                
                # 跳过空URL
                if not item_url:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 跳过空URL")
                    continue
                
                # 请求每个url的数据
                config_response = requests.get(item_url, headers=headers, timeout=20)
                config_response.raise_for_status()
                # 处理响应内容，替换特殊字符
                formatted_content = format_response_content(config_response.content)

                final_content = replace_content(formatted_content)

                if final_content is None or len(final_content) == 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 无法格式化响应内容，跳过: {item_url}")
                    continue

                # 提取文件名（从url的最后部分）
                # 例如：https://example.com/config.json -> config.json
                file_name = item_url.split('/')[-1]
                
                # 确保文件名有效
                if not file_name:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 无法提取文件名，跳过: {item_url}")
                    continue

                # 如果文件名不是.json结尾，需要加上
                if not file_name.endswith('.json'):
                    file_name += '.json'

                # 保存数据到文件
                file_path = os.path.join(TVBOX_DIR, file_name)
                try:
                    with open(file_path, 'wb') as f:
                        f.write(final_content)
                    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 成功保存文件: {file_name}")

                    # 更新new_item的url
                    new_item['url'] = f"http://localhost/api/tvbox/{file_name}"    
                    # 将name中的游魂替换为万家
                    new_item['name'] = new_item['name'].replace('游魂', '万家')
                    
                    new_urls.append(new_item)   

                except Exception as e:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 保存文件失败: {file_name}, 错误: {str(e)}")

                # 等待1秒，避免对服务器 too many requests
                time.sleep(1)
                
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 处理URL失败: {item_url}, 错误: {str(e)}")
        
        # 将修改后的urls列表赋值回data对象
        data['urls'] = new_urls

        # 将修改后的data对象保存回config.json文件
        with open(os.path.join(TVBOX_DIR, "config.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 配置更新完成")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TVBox] 更新失败: {str(e)}")

def format_response_content(content):
    """
    格式化响应内容，替换特殊字符
    """
    try:
        # 解码内容，使用 utf-8-sig 自动移除 BOM
        content_str = content.decode('utf-8-sig')
        
        # 检查内容是否为空
        if not content_str.strip():
            #print("[TVBox] 响应内容为空")
            return None
        
        # 尝试直接解析JSON
        try:
            data = json.loads(content_str)
            # 格式化为json字符串
            return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        except json.JSONDecodeError as e:
            #print(f"[TVBox] 直接解析JSON失败: {e}")
            # 尝试清理内容后再解析
            try:
                # 初始化cleaned_content变量
                cleaned_content = content_str
                
                # 移除content中的注释（/* */ 中的内容）
                # 注意：不使用//.*?\n，因为这会破坏URL中的//
                cleaned_content = re.sub(r'/\*.*?\*/', '', cleaned_content, flags=re.DOTALL)
                
                # 移除行尾的注释（不包含URL中的//）
                # 只移除以//开头的行注释，避免影响URL
                lines = cleaned_content.split('\n')
                cleaned_lines = []
                for line in lines:
                    # 只移除行首的//注释，保留URL中的//
                    stripped_line = line.lstrip()
                    if not stripped_line.startswith('//'):
                        cleaned_lines.append(line)
                cleaned_content = '\n'.join(cleaned_lines)
                
                # 移除多余的空白字符，但保留必要的空格
                # 不使用\s+，因为这会破坏JSON格式
                cleaned_content = ' '.join(cleaned_content.split())
    
                # 尝试解析清理后的内容
                data = json.loads(cleaned_content)
                #print("[TVBox] 清理后成功解析为JSON")
                # 格式化为json字符串
                return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            except json.JSONDecodeError as e:
                print(f"[TVBox] 清理后解析JSON仍然失败: {e}")
                return None
    except Exception as e:
        print(f"[TVBox] 处理响应内容时发生错误: {e}")
        return None


# 要匹配的关键字
REPLACE_KEYWORDS = ['Douban','豆瓣',"豆","豆豆"]

def replace_content(content):
    """
    过滤响应内容，移除特殊字符
    """
    # 解析JSON
    data = json.loads(content)
    
    # 获取sites数组
    sites = data.get('sites', [])

    if sites is None or len(sites) == 0:
        return None

    # 如果warningText这个字段存在，则移除它
    if 'warningText' in data:
        del data['warningText']

    # 遍历sites数组
    for site in sites:
        # 检查key或name是否包含指定关键字
        key = site.get('key', '')
        name = site.get('name', '')

        # 如果key等于push_agent，则删除该站点
        if key == "push_agent":
            sites.remove(site)
            #print(f"  匹配到站点: key='{key}', name='{name}', 已成功删除")
            continue

        for keyword in REPLACE_KEYWORDS:
            if keyword == key:
                # 修改原始字典中的name值
                site['name'] = "🚀豆瓣┃热播"
                #print(f"  匹配到站点: key='{key}', name='{name}', 匹配关键字: '{keyword}'，已成功设置为 '🚀豆瓣┃热播'")
                break
    
    # 返回修改后的数据
    return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        
if __name__ == "__main__":
    tvbox_scheduler()