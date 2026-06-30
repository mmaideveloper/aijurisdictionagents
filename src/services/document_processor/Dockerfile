FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

# The document processor runs CPU-only in self-managed prod. Preinstalling
# torch from the official CPU wheel index prevents PyPI's CUDA dependency set
# from turning routine deploys into multi-GB downloads.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.3"
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.document_processor", "--limit", "20"]
