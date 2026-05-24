"""
同步 output 目录到 GitHub Gist

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
    
    # Gist 的 git URL（使用 token 认证）
    gist_url = f"https://{token}@gist.github.com/{gist_id}.git"
    
    # 临时目录用于克隆和同步
    temp_dir = os.path.join(project_root, "temp_gist_sync")
    
    try:
        # 清理临时目录
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir], check=True)
        
        # 克隆 Gist
        print(f"正在克隆 Gist: {gist_id}")
        subprocess.run(
            ["git", "clone", gist_url, temp_dir],
            check=True,
            capture_output=True
        )
        
        # 清理 Gist 中的旧文件
        print("清理 Gist 中的旧文件...")
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if item != ".git":
                if os.path.isdir(item_path):
                    subprocess.run(["rm", "-rf", item_path], check=True)
                else:
                    os.remove(item_path)
        
        # 复制 output 目录内容到 Gist
        print(f"复制 {output_dir} 目录内容...")
        for item in os.listdir(output_path):
            src_path = os.path.join(output_path, item)
            dst_path = os.path.join(temp_dir, item)
            
            if os.path.isdir(src_path):
                subprocess.run(["cp", "-r", src_path, dst_path], check=True)
            else:
                subprocess.run(["cp", src_path, dst_path], check=True)
        
        # 配置 git
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
        
        # 检查是否有更改
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=temp_dir,
            capture_output=True
        )
        
        if result.returncode == 0:
            print("没有更改，跳过提交")
            return True
        
        # 添加并提交
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Sync output directory - {os.popen('date').read().strip()}"],
            cwd=temp_dir,
            check=True
        )
        
        # 推送
        print("推送更改到 Gist...")
        subprocess.run(["git", "push", "origin", "master"], cwd=temp_dir, check=True)
        
        print("同步完成！")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        return False
    finally:
        # 清理临时目录
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