import os
import json
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CONFIG
from utils.logger import get_logger

TVBOX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'tvbox')
TVBOX_URL = CONFIG.tvbox.url
headers = {"User-Agent": "okhttp/3.12.12", "Accept": "application/json"}
os.makedirs(TVBOX_DIR, exist_ok=True)

logger = get_logger('TVBOX')
MAX_WORKERS = 10

REPLACE_KEYWORDS = ['csp_DouDouGuard', 'csp_Douban', 'csp_DouDou', 'csp_DoubanGuard']


def process_single_url(item):
    """处理单个URL，返回处理结果或None"""
    item_url = item.get('url', '')
    if not item_url:
        logger.warning("跳过空URL")
        return None
    
    try:
        new_item = item.copy()
        config_response = requests.get(item_url, headers=headers, timeout=20)
        config_response.raise_for_status()
        formatted_content = format_response_content(config_response.content)
        final_content = replace_content(formatted_content)
        
        if final_content is None or len(final_content) == 0:
            # logger.warning(f"无法格式化响应内容，跳过: {item_url}")
            return None
        
        file_name = item_url.split('/')[-1]
        if not file_name:
            logger.warning(f"无法提取文件名，跳过: {item_url}")
            return None
        
        if not file_name.endswith('.json'):
            file_name += '.json'
        
        file_path = os.path.join(TVBOX_DIR, file_name)
        with open(file_path, 'wb') as f:
            f.write(final_content)
        
        new_item['url'] = f"https://localhost/api/tvbox/{file_name}"
        new_item['name'] = new_item['name'].replace('游魂', '万家')
        return new_item
        
    except Exception as e:
        # logger.error(f"处理URL失败: {item_url}, 错误: {str(e)}")
        return None


def tvbox_scheduler():
    logger.info(f"开始更新配置，时间: {datetime.now().isoformat()}")
    
    try:
        response = requests.get(TVBOX_URL, headers=headers, timeout=20)
        response.raise_for_status()
        
        data = response.json()
        if data is None or 'urls' not in data:
            logger.error("主接口返回数据格式错误")
            return
        
        urls = data.get('urls', [])
        # logger.info(f"成功获取 {len(urls)} 个配置URL")
        
        new_urls = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_single_url, item): item for item in urls}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    new_urls.append(result)
        
        data['urls'] = new_urls
        with open(os.path.join(TVBOX_DIR, "config.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"配置更新完成，成功: {len(new_urls)}/{len(urls)}，时间: {datetime.now().isoformat()}")
        
    except Exception as e:
        logger.error(f"更新失败: {str(e)}")


def format_response_content(content):
    try:
        content_str = content.decode('utf-8-sig')
        if not content_str.strip():
            return None
        
        try:
            data = json.loads(content_str)
            return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        except json.JSONDecodeError:
            try:
                cleaned_content = re.sub(r'/\*.*?\*/', '', content_str, flags=re.DOTALL)
                lines = cleaned_content.split('\n')
                cleaned_lines = [line for line in lines if not line.lstrip().startswith('//')]
                cleaned_content = '\n'.join(cleaned_lines)
                cleaned_content = ' '.join(cleaned_content.split())
                data = json.loads(cleaned_content)
                return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            except json.JSONDecodeError as e:
                # logger.error(f"清理后解析JSON仍然失败: {e}")
                return None
    except Exception as e:
        # logger.error(f"处理响应内容时发生错误: {e}")
        return None


def replace_content(content):
    try:
        data = json.loads(content)
        sites = data.get('sites', [])
        
        if sites is None or len(sites) == 0:
            return None
        
        if 'warningText' in data:
            del data['warningText']
        
        new_name = "🚀豆瓣┃热播"
        
        for site in sites:
            api_key = site.get('api', '')
            if api_key == "push_agent":
                sites.remove(site)
                continue
            for keyword in REPLACE_KEYWORDS:
                if keyword == api_key:
                    site['name'] = new_name
                    break
        
        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    except Exception as e:
        # logger.error(f"替换内容失败: {e}")
        return None


if __name__ == "__main__":
    tvbox_scheduler()
