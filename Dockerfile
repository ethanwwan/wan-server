# ============================================================
# Stage 1: Builder - 安装依赖到独立目录
# ============================================================
FROM python:3.12-alpine AS builder

WORKDIR /build

# 系统依赖（编译阶段需要 gcc/musl-dev，运行时不需要）
RUN apk add --no-cache gcc musl-dev

# 先复制 requirements.txt，利用 Docker 缓存（依赖不变就不重装）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# Stage 2: Runtime - 仅复制必要的 Python 包和代码
# ============================================================
FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai \
    PATH=/home/user/.local/bin:$PATH

# 从 builder 阶段复制已安装的 Python 包（避免重新安装系统依赖）
COPY --from=builder /root/.local /home/user/.local

# 复制项目代码
COPY . .

# 创建非 root 用户运行（安全最佳实践）
RUN adduser -D -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8016

CMD ["python", "main.py"]
