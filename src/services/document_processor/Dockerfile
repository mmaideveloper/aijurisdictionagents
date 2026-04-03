FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir .
RUN mkdir -p /app/aimodels

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.document_processor", "--limit", "20"]
