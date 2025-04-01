FROM openeuler/openeuler:22.03

WORKDIR /app

COPY requirements.txt .

RUN dnf update -y && \
    dnf install -y \
        python3 \
        python3-devel \
        python3-pip \
        gcc \
        gcc-c++ \
        make \
        libffi-devel \
        git && \
    dnf install -y libstdc++ libffi && \
    pip install --no-cache-dir gunicorn uvicorn && \
    pip install --no-cache-dir -r requirements.txt && \
    adduser -u 1000 repair-robt && \
    chown -R repair-robt:repair-robt /app && \
    dnf remove -y \
        python3-devel \
        gcc \
        gcc-c++ \
        make \
        libffi-devel && \
    dnf clean all


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER repair-robt
COPY --chown=repair-robt:repair-robt . .

EXPOSE 8080

CMD ["gunicorn", "app.main:app", \
     "--timeout", "0", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "32", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--worker-tmp-dir", "/dev/shm", \
     "--preload"]
