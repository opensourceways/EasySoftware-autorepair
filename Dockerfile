FROM python:3.11-alpine AS builder

RUN mkdir -p /tmp /var/tmp /usr/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp

RUN mkdir -p /app/tmp && \
    chmod 777 /app/tmp

WORKDIR /app

RUN apk update && \
    apk add --no-cache --virtual .build-deps \
    python3-dev \
    musl-dev \
    gcc \
    g++ \
    make \
    libffi-dev && \
    apk add --no-cache \
    libstdc++ \
    libffi

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-alpine

# 复制构建结果（关键优化步骤）
COPY --from=builder /app /app
COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TMPDIR=/app/tmp

RUN mkdir -p /app/tmp && \
    chmod 777 /app/tmp && \
    adduser -D -u 1000 repair-robt && \
    chown -R repair-robt:repair-robt /app

WORKDIR /app
USER repair-robt

EXPOSE 8080

CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--preload"]