FROM python:3.13-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY aimodels /app/aimodels
COPY src /app/src

# The document processor runs CPU-only in self-managed prod. Preinstalling
# torch from the official CPU wheel index prevents PyPI's CUDA dependency set
# from turning routine deploys into multi-GB downloads. Keep the exact installed
# build constrained while installing the app, otherwise transitive dependencies
# can upgrade torch back to a CUDA-enabled PyPI build.
RUN pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple "numpy>=2.1,<2.4" && \
    cpu_torch_requirement="torch>=2.3,<2.8" && \
    if [ "$(uname -m)" = "x86_64" ]; then cpu_torch_requirement="https://download.pytorch.org/whl/cpu/torch-2.7.1%2Bcpu-cp313-cp313-manylinux_2_28_x86_64.whl#sha256=84ea1f6a1d15663037d01b121d6e33bb9da3c90af8e069e5072c30f413455a57"; fi && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://download.pytorch.org/whl/cpu "$cpu_torch_requirement"
RUN python -c "import numpy, torch; print(f'numpy=={numpy.__version__}'); print(f'torch=={torch.__version__}')" > /tmp/runtime-constraints.txt && \
    printf '%s\n' 'onnxruntime==1.27.0' 'opencv-python==4.13.0.92' >> /tmp/runtime-constraints.txt && \
    pip install --no-cache-dir --retries "$PIP_RETRIES" --timeout "$PIP_DEFAULT_TIMEOUT" --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --constraint /tmp/runtime-constraints.txt .

RUN HF_HUB_OFFLINE=1 python -c "from sentence_transformers import SentenceTransformer; print('CPU embedding import passed')"

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.document_processor", "--limit", "20"]
