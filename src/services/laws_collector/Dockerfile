FROM python:3.13-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

# The root package depends on sentence-transformers. Preinstalling and
# constraining CPU torch prevents PyPI from resolving CUDA-enabled wheels.
RUN pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple "numpy>=2.1,<2.4" && \
    cpu_torch_requirement="torch>=2.3,<2.8" && \
    if [ "$(uname -m)" = "x86_64" ]; then cpu_torch_requirement="https://download.pytorch.org/whl/cpu/torch-2.7.1%2Bcpu-cp313-cp313-manylinux_2_28_x86_64.whl#sha256=84ea1f6a1d15663037d01b121d6e33bb9da3c90af8e069e5072c30f413455a57"; fi && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://download.pytorch.org/whl/cpu "$cpu_torch_requirement"
RUN python -c "import numpy, torch; print(f'numpy=={numpy.__version__}'); print(f'torch=={torch.__version__}')" > /tmp/runtime-constraints.txt && \
    printf '%s\n' 'onnxruntime==1.27.0' 'opencv-python==4.13.0.92' >> /tmp/runtime-constraints.txt && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --constraint /tmp/runtime-constraints.txt .

RUN HF_HUB_OFFLINE=1 python -c "from sentence_transformers import SentenceTransformer; print('CPU embedding import passed')"

ENV PYTHONUNBUFFERED=1
ENV LAWS_WORKER_FIXTURE=baseline
ENV LAWS_WORKER_POLL_SECONDS=3600

CMD ["python", "-c", "from services.laws_collector.worker import run_worker; run_worker()"]
