FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --create-home appuser

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=appuser:appgroup app.py ./
COPY --chown=appuser:appgroup data_report_api ./data_report_api
RUN mkdir -p /app/var/risk-uploads && chown -R appuser:appgroup /app/var

USER appuser
EXPOSE 5160

CMD ["gunicorn", "--bind", "0.0.0.0:5160", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
