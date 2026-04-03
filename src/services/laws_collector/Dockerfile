FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir .
RUN mkdir -p /app/aimodels

ENV PYTHONUNBUFFERED=1
ENV LAWS_WORKER_FIXTURE=baseline
ENV LAWS_WORKER_POLL_SECONDS=3600

CMD ["python", "-c", "from services.laws_collector.worker import run_worker; run_worker()"]
