FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.document_processor", "--limit", "20"]
