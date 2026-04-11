from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LocalModelBuildRequest:
    country_code: str
    base_model: str = "meta-llama/Meta-Llama-3-13B-Instruct"
    adapter_name: str = "lora-slovak-legal"
    quantization: str = "gguf-q4_k_m"


@dataclass(frozen=True)
class LocalModelBuildResult:
    model_name: str
    model_version: str
    model_cutoff_time: datetime
    last_processed_law: str
    training_documents: int
    output_dir: Path
    modelfile_path: Path
    metadata_path: Path
