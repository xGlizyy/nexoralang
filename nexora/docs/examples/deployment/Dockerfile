FROM python:3.13.18-slim@sha256:b3575dcf816cdacc5292df77a6e3e59b8941631078373a045efa2ac1e9c5c3b2

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
