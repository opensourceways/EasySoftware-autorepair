FROM openeuler/openeuler:24.03-lts

RUN mkdir -p /tmp /var/tmp /usr/tmp /app/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp && \
    chmod 777 /app /app/tmp

WORKDIR /app

COPY requirements.txt .

RUN dnf update -y && \
    dnf install -y \
        python3.9 \
        python3-devel \
        python3-pip \
        gcc \
        gcc-c++ \
        make \
        libffi-devel && \
    dnf install -y libstdc++ libffi && \
    pip install --upgrade pip && \
    pip install --no-cache-dir gunicorn uvicorn && \
    pip install --no-cache-dir -r requirements.txt && \
    useradd -M -u 1000 repair-robt && \
    chown -R repair-robt:repair-robt /app && \
    dnf remove -y \
        python3-devel \
        gcc \
        gcc-c++ \
        make \
        libffi-devel && \
    dnf clean all


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
