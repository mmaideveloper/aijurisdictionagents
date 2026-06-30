FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

# The laws collector runs CPU-only in self-managed prod. Preinstalling torch
# from the CPU wheel index prevents PyPI's CUDA dependency set from turning
# deploys into multi-GB downloads, and the constraint keeps transitive
# dependencies from replacing it.
RUN pip install --no-cache-dir "numpy>=2.1,<2.4" && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.3,<2.8"
RUN python -c "import torch; print(f'torch=={torch.__version__}')" > /tmp/torch-constraint.txt && \
    pip install --no-cache-dir --constraint /tmp/torch-constraint.txt .

ENV PYTHONUNBUFFERED=1
ENV LAWS_WORKER_FIXTURE=baseline
ENV LAWS_WORKER_POLL_SECONDS=3600

CMD ["python", "-c", "from services.laws_collector.worker import run_worker; run_worker()"]
