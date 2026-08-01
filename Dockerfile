# Multi-stage build: install deps in a builder layer, copy a slim runtime image.
FROM python:3.12-slim AS builder

WORKDIR /build

COPY app/requirements.txt requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim AS runtime

WORKDIR /srv/app

COPY --from=builder /install /usr/local

COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY extensions/ extensions/
COPY start.sh start.sh

ENV DATABASE_PATH=/data/job_tracker.db
ENV HOST=0.0.0.0
ENV PORT=9000
ENV JOB_TRACKER_SKIP_VENV=1
EXPOSE 9000

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chmod +x /srv/app/start.sh \
    && chown -R appuser:appuser /data /srv/app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request as u; u.urlopen('http://127.0.0.1:9000/health', timeout=3)" || exit 1

CMD ["./start.sh"]
