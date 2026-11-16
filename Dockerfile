FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd -g 10001 rovuma && useradd -m -u 10001 -g 10001 rovuma \
    && install -o rovuma -g rovuma -d /data/private /data/spool /app/static-build
COPY --chown=rovuma:rovuma . .

FROM base AS web
USER rovuma
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "90", "rovuma.wsgi:application"]

FROM base AS processor
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer fonts-dejavu-core fonts-liberation clamav \
    && rm -rf /var/lib/apt/lists/*
USER rovuma
CMD ["python", "-m", "documents.worker", "--spool", "/data/spool"]
