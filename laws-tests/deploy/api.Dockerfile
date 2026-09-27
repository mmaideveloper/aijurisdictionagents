FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src/ src/
# The fixed-answer service reuses core adapters without OCR/embedding/agent dependencies.
RUN --mount=type=secret,id=build_ca if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; pip install --no-cache-dir --no-deps .
COPY laws-tests/api/ laws-tests/api/
RUN --mount=type=secret,id=build_ca if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; pip install --no-cache-dir ./laws-tests/api
COPY databases/laws-tests/ databases/laws-tests/
COPY laws-tests/deploy/migrate_release.py laws-tests/deploy/migrate_release.py
COPY laws-tests/deploy/smoke_identity.py laws-tests/deploy/smoke_identity.py
RUN useradd --uid 10840 --create-home laws-tests && mkdir -p /app/runs/storage/laws-tests/blobs && chown -R laws-tests /app/runs
USER laws-tests
ENV PYTHONUNBUFFERED=1 LOCAL_LLM_IO_LOGGING=0
EXPOSE 8000
CMD ["uvicorn", "laws_tests.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
