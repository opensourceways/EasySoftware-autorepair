# 使用alpine镜像更小巧（可选，根据依赖兼容性决定）
FROM python:3.11-alpine AS builder

# 创建非root用户（提升安全性）
RUN adduser -D -u 1000 repair-robt

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 安装系统依赖（根据项目需要调整，如gcc/postgresql-dev等）
RUN apk add --no-cache gcc musl-dev libffi-dev

# 先单独复制依赖文件，利用Docker层缓存
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目代码（确保已配置.dockerignore）
COPY . .

# 切换用户
USER repair-robt

# 生产环境移除--reload，建议用gunicorn+uvicorn workers
CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker"]
