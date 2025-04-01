FROM python:3.9-alpine

RUN mkdir -p /tmp /var/tmp /usr/tmp /app/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp && \
    chmod 777 /app /app/tmp

WORKDIR /app

COPY requirements.txt .

RUN apk update && \
    apk add --no-cache --virtual .build-deps \
        python3-dev \
        musl-dev \
        gcc \
        g++ \
        make \
        libffi-dev && \
    apk add --no-cache libstdc++ libffi && \
    pip install --upgrade pip && \
    pip install --no-cache-dir gunicorn uvicorn && \
    pip install --no-cache-dir -r requirements.txt && \
    adduser -D -u 1000 repair-robt && \
    chown -R repair-robt:repair-robt /app && \
    apk del .build-deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp

USER repair-robt
COPY --chown=repair-robt:repair-robt . .

EXPOSE 8080

# 打印当前工作目录下的文件
RUN echo "Files in /app:" && ls -l /app

# 打印当前 /tmp 目录下的文件
RUN echo "Files in /tmp:" && ls -l /tmp

CMD ["gunicorn", "app.main:app", \
     "--timeout", "120", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--worker-tmp-dir", "/dev/shm", \
     "--preload"]
