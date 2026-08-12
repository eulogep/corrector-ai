# Image de production Corrector AI.
# Le build exige un environnement Docker Linux avec au moins 4 Go de RAM disponibles
# pour l'installation et le premier chargement de certains composants Docling.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/model-cache \
    TRANSFORMERS_CACHE=/data/model-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 corrector \
    && useradd --system --uid 10001 --gid corrector --home-dir /app --shell /usr/sbin/nologin corrector

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install --requirement backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY docker/entrypoint.sh /usr/local/bin/corrector-entrypoint

RUN chmod 0555 /usr/local/bin/corrector-entrypoint \
    && mkdir -p /data/uploads /data/reports /data/model-cache \
    && chown -R corrector:corrector /app /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

ENTRYPOINT ["/usr/local/bin/corrector-entrypoint"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
