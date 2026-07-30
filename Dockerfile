# ============================================================
# Stage 1: Builder - 在标准目录编译安装依赖
# ============================================================
FROM python:3.12-alpine AS builder

WORKDIR /build

# 编译工具（运行时丢弃）
RUN apk add --no-cache gcc musl-dev

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================================
# Stage 2: Runtime - 标准 Python 环境
# ============================================================
FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

# Alpine 时区数据
RUN apk add --no-cache tzdata

# 从 builder 阶段复制系统 site-packages（标准位置 /usr/local/lib/python3.12/...）
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY . .

EXPOSE 8016

CMD ["python", "main.py"]
