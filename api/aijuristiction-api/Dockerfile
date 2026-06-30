FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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
    pip install --no-cache-dir "numpy>=2.1,<2.4" && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.3,<2.8" && \
    pip install --no-cache-dir -e . && \
    pip install --no-cache-dir -e ./api/aijuristiction-api

USER app

WORKDIR /workspace/api/aijuristiction-api

EXPOSE 8080 8070

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
