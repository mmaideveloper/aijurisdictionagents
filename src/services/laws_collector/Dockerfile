FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

# The root package depends on sentence-transformers. Preinstalling and
# constraining CPU torch prevents PyPI from resolving CUDA-enabled wheels.
RUN pip install --no-cache-dir "numpy>=2.1,<2.4" && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.3,<2.8"
RUN python -c "import numpy, torch; print(f'numpy=={numpy.__version__}'); print(f'torch=={torch.__version__}')" > /tmp/runtime-constraints.txt && \
    pip install --no-cache-dir --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --constraint /tmp/runtime-constraints.txt .

ENV PYTHONUNBUFFERED=1
ENV LAWS_WORKER_FIXTURE=baseline
ENV LAWS_WORKER_POLL_SECONDS=3600

CMD ["python", "-c", "from services.laws_collector.worker import run_worker; run_worker()"]
