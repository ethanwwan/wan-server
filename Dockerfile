# 使用官方Python 3.12基础镜像，并通过--platform指定x86_64架构
FROM python:3.12-slim

# 安装 ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制requirements.txt文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建public目录（用于保存配置文件）
RUN mkdir -p public

# 定义启动命令
CMD ["python", "main.py"]