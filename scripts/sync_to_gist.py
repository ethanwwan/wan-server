"""
同步 output 目录到 GitHub Gist

注意：Gist 不支持目录结构，所以会将目录平铺

使用方法：
python scripts/sync_to_gist.py --gist-id <gist_id> --token <github_token>

环境变量：
- GIST_ID: Gist ID
- GITHUB_TOKEN: GitHub 访问令牌（需要 gist 权限）
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def sync_to_gist(gist_id: str, token: str, output_dir: str = "output"):
    """
    同步 output 目录到 Gist
    
    Args:
        gist_id: Gist ID
        token: GitHub 访问令牌
        output_dir: 要同步的目录
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, output_dir)
    
    if not os.path.exists(output_path):
        print(f"错误：目录不存在: {output_path}")
        return False
    
    gist_url = f"https://{token}@gist.github.com/{gist_id}.git"
    temp_dir = os.path.join(project_root, "temp_gist_sync")
    
    try:
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir], check=True)
        
        print(f"正在克隆 Gist: {gist_id}")
        subprocess.run(
            ["git", "clone", gist_url, temp_dir],
            check=True,
            capture_output=True
        )
        
        print("清理 Gist 中的旧文件...")
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if item != ".git":
                if os.path.isdir(item_path):
                    subprocess.run(["rm", "-rf", item_path], check=True)
                else:
                    os.remove(item_path)
        
        print(f"复制 {output_dir} 目录内容（平铺目录结构）...")
        for root, dirs, files in os.walk(output_path):
            for filename in files:
                # 跳过隐藏文件和缓存文件
                if filename.startswith('.') or filename.endswith('~'):
                    continue
                
                src_path = os.path.join(root, filename)
                
                # 计算相对路径并转换为下划线格式
                rel_path = os.path.relpath(src_path, output_path)
                # 将路径分隔符替换为下划线
                flat_name = rel_path.replace(os.sep, '_')
                
                dst_path = os.path.join(temp_dir, flat_name)
                subprocess.run(["cp", src_path, dst_path], check=True)
                print(f"  {rel_path} → {flat_name}")
        
        subprocess.run(
            ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
            cwd=temp_dir,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "github-actions[bot]"],
            cwd=temp_dir,
            check=True
        )
        
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=temp_dir,
            capture_output=True
        )
        
        if result.returncode == 0:
            print("没有更改，跳过提交")
            return True
        
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Sync output directory - {os.popen('date').read().strip()}"],
            cwd=temp_dir,
            check=True
        )
        
        print("推送更改到 Gist...")
        subprocess.run(["git", "push", "origin", "main"], cwd=temp_dir, check=True)
        
        print("同步完成！")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        return False
    finally:
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir], capture_output=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="同步 output 目录到 Gist")
    parser.add_argument("--gist-id", required=True, help="Gist ID")
    parser.add_argument("--token", required=True, help="GitHub 访问令牌")
    parser.add_argument("--output-dir", default="output", help="要同步的目录")
    
    args = parser.parse_args()
    
    success = sync_to_gist(args.gist_id, args.token, args.output_dir)
    sys.exit(0 if success else 1)