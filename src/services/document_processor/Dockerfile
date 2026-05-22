FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.document_processor", "--limit", "20"]
