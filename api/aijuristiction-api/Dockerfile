FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /workspace

RUN apt-get update && \
    apt-get install --yes --no-install-recommends fonts-dejavu-core poppler-utils && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY databases ./databases
COPY mobile_app/pubspec.yaml ./mobile_app/pubspec.yaml
COPY api/aijuristiction-api ./api/aijuristiction-api

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple "numpy>=2.1,<2.4" && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://download.pytorch.org/whl/cpu "torch>=2.3,<2.8" && \
    python -c "import numpy, torch; print(f'numpy=={numpy.__version__}'); print(f'torch=={torch.__version__}')" > /tmp/runtime-constraints.txt && \
    printf '%s\n' \
      'opentelemetry-exporter-otlp==1.40.0' \
      'opentelemetry-exporter-otlp-proto-common==1.40.0' \
      'opentelemetry-exporter-otlp-proto-grpc==1.40.0' \
      'opentelemetry-exporter-otlp-proto-http==1.40.0' \
      'opentelemetry-proto==1.40.0' \
      'onnxruntime==1.27.0' \
      'opencv-python==4.13.0.92' >> /tmp/runtime-constraints.txt && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --constraint /tmp/runtime-constraints.txt -e . && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --constraint /tmp/runtime-constraints.txt -e ./api/aijuristiction-api

USER app

WORKDIR /workspace/api/aijuristiction-api

EXPOSE 8080 8070

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
