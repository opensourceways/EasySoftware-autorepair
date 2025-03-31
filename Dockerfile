FROM python:3.11-alpine AS builder

# 创建系统级临时目录（解决musl兼容性问题）
RUN mkdir -p /tmp /var/tmp /usr/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp

# 创建应用专属临时目录
RUN mkdir -p /app/tmp

RUN adduser -D -u 1000 repair-robt && \
    chown repair-robt:repair-robt /app/tmp && \
    chmod 700 /app/tmp

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update \
  && apk add --no-cache \
    python3 python3-dev \
    musl-dev gcc g++ make \
    libffi libffi-dev libstdc++ \
    py3-gevent py3-gunicorn py3-wheel \
    py3-pip \
 && apk del python3-dev musl-dev gcc g++ make libffi-dev

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

USER repair-robt

EXPOSE 8080

# 添加--preload参数提升稳定性
CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--preload"]
