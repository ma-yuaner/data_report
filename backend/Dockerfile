ARG DOCKERHUB_MIRROR=docker.io
FROM ${DOCKERHUB_MIRROR}/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --create-home appuser

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=appuser:appgroup app.py ./
COPY --chown=appuser:appgroup data_report_api ./data_report_api
RUN mkdir -p /app/var/risk-uploads /app/var/comprehensive-exports /app/var/data-workbench /app/var/hr-mail \
    && chown -R appuser:appgroup /app/var

USER appuser
EXPOSE 5160

CMD ["gunicorn", "--bind", "0.0.0.0:5160", "--workers", "2", "--threads", "4", "--timeout", "1800", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
