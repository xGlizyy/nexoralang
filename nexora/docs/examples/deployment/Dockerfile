FROM python:3.13.18-slim@sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --no-compile -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p config \
    && chown appuser:appuser config

COPY app.nex ./app.nex
COPY config/app.conf.example ./config/app.conf.example
USER 10001:10001

CMD ["nex", "run", "app.nex", "--allow-read", "config/app.conf"]
