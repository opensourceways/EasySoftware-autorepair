FROM python:3.11-alpine AS builder

RUN mkdir -p /tmp /var/tmp /usr/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp

WORKDIR /app

RUN apk update && \
    apk add --no-cache --virtual .build-deps \
    python3-dev \
    musl-dev \
    gcc \
    g++ \
    make \
    libffi-dev

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir gunicorn uvicorn && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11-alpine

RUN apk update && \
    apk add --no-cache libstdc++ libffi

COPY --from=builder /usr/lib/python3.11/site-packages /usr/lib/python3.11/site-packages
COPY --from=builder /usr/bin/gunicorn /usr/bin/gunicorn
COPY --from=builder /usr/bin/uvicorn /usr/bin/uvicorn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/app/tmp

RUN mkdir -p /app/tmp && \
    chmod 777 /app/tmp && \
    adduser -D -u 1000 repair-robt && \
    chown -R repair-robt:repair-robt /app

WORKDIR /app
USER repair-robt

COPY --chown=repair-robt:repair-robt . .

EXPOSE 8080

CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--preload"]
