FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/data/db.sqlite SURVEYS_DIR=/data/surveys \
    HOME=/tmp MPLCONFIGDIR=/tmp/matplotlib XDG_CACHE_HOME=/tmp/cache
WORKDIR /app
# WeasyPrint: Pango/HarfBuzz; Schriften für PDF-Auswertung (DejaVu) und TAN-Bögen (Liberation statt Arial)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY app ./app
COPY static ./static
COPY surveys ./surveys
COPY locales ./locales
RUN groupadd --gid 10001 schuleva && useradd --uid 10001 --gid 10001 --no-create-home schuleva \
    && mkdir -p /data/surveys && chown -R 10001:10001 /data && chmod 700 /data
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.serve"]

FROM runtime AS tests
USER 0
COPY requirements-test.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-test.lock
COPY tests ./tests
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"]

FROM runtime AS final
