FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV LAWS_WORKER_FIXTURE=baseline
ENV LAWS_WORKER_POLL_SECONDS=3600

CMD ["python", "-c", "from services.laws_collector.worker import run_worker; run_worker()"]
