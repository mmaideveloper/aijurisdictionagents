FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATABASE_URL=sqlite:////tmp/document_engine.db \
    GENERATED_DOCUMENTS_DIR=/tmp/generated-documents

WORKDIR /app

COPY requirements.txt ./
COPY src ./src

RUN pip install \
    --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "document_engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
