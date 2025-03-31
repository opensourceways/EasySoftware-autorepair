FROM python:3.11-alpine AS builder

# 创建系统级临时目录（解决musl兼容性问题）
RUN mkdir -p /tmp /var/tmp /usr/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp

# 创建应用专属临时目录
RUN mkdir -p /app/tmp && \
    chmod 700 /app/tmp

RUN adduser -D -u 1000 repair-robt && \
    chown repair-robt:repair-robt /app/tmp

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TMPDIR /app/tmp

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    libstdc++ \
    openssl \
    tzdata

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

USER repair-robt

# 添加--preload参数提升稳定性
CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--preload"]
