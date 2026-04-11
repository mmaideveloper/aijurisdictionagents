from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .config import LocalModelBuilderConfig
from .domain import LocalModelBuildRequest, LocalModelBuildResult
from .sqlite_store import LocalModelSqliteStore


class LocalModelBuilderService:
    """Build country-scoped local model bundles from the laws corpus metadata."""

    def __init__(self, *, config: LocalModelBuilderConfig, store: LocalModelSqliteStore) -> None:
        self.config = config
        self.store = store

    @classmethod
    def from_config(cls, *, config: LocalModelBuilderConfig) -> "LocalModelBuilderService":
        store = LocalModelSqliteStore(
            metadata_db_path=config.resolved_metadata_db_path,
            migration_path=config.resolved_sql_assets_root / "0001_create_local_model_builder_tables.sql",
        )
        return cls(config=config, store=store)

    def build_country_model(self, request: LocalModelBuildRequest) -> LocalModelBuildResult:
        self.store.ensure_schema()
        summary = self.store.read_law_corpus_summary(
            laws_db_path=self.config.resolved_laws_db_path,
            country_code=request.country_code,
        )

        model_name = f"aj-{request.country_code.lower()}-laws-local"
        model_cutoff_time = summary.latest_updated_at.astimezone(timezone.utc)
        timestamp = datetime.now(tz=timezone.utc)
        model_version = timestamp.strftime("%Y%m%d%H%M%S")

        output_dir = self.config.resolved_output_root / request.country_code.lower() / model_version
        output_dir.mkdir(parents=True, exist_ok=True)

        modelfile_path = self._write_modelfile(
            output_dir=output_dir,
            request=request,
            model_name=model_name,
            model_version=model_version,
            model_cutoff_time=model_cutoff_time,
            last_processed_law=summary.last_processed_law,
        )
        metadata_path = self._write_metadata(
            output_dir=output_dir,
            request=request,
            model_name=model_name,
            model_version=model_version,
            model_cutoff_time=model_cutoff_time,
            last_processed_law=summary.last_processed_law,
            training_documents=summary.total_documents,
        )

        self.store.persist_model_build(
            country_code=request.country_code,
            model_name=model_name,
            model_version=model_version,
            model_cutoff_time=model_cutoff_time,
            last_processed_law=summary.last_processed_law,
            base_model=request.base_model,
            adapter_name=request.adapter_name,
            quantization=request.quantization,
            training_documents=summary.total_documents,
            output_format="gguf",
            output_uri=str(output_dir),
        )

        return LocalModelBuildResult(
            model_name=model_name,
            model_version=model_version,
            model_cutoff_time=model_cutoff_time,
            last_processed_law=summary.last_processed_law,
            training_documents=summary.total_documents,
            output_dir=output_dir,
            modelfile_path=modelfile_path,
            metadata_path=metadata_path,
        )

    def _write_modelfile(
        self,
        *,
        output_dir: Path,
        request: LocalModelBuildRequest,
        model_name: str,
        model_version: str,
        model_cutoff_time: datetime,
        last_processed_law: str,
    ) -> Path:
        content = (
            f"FROM {request.base_model}\n"
            f"ADAPTER ./adapters/{request.adapter_name}.safetensors\n"
            f"PARAMETER quantization {request.quantization}\n"
            f"SYSTEM You are {model_name}:{model_version} trained on {request.country_code} laws "
            f"up to {model_cutoff_time.isoformat()} and last law {last_processed_law}.\n"
        )
        modelfile_path = output_dir / "Modelfile"
        modelfile_path.write_text(content, encoding="utf-8")
        return modelfile_path

    def _write_metadata(
        self,
        *,
        output_dir: Path,
        request: LocalModelBuildRequest,
        model_name: str,
        model_version: str,
        model_cutoff_time: datetime,
        last_processed_law: str,
        training_documents: int,
    ) -> Path:
        manifest = {
            "model_name": model_name,
            "model_version": model_version,
            "country_code": request.country_code,
            "base_model": request.base_model,
            "adapter": {
                "name": request.adapter_name,
                "method": "LoRA",
            },
            "quantization": request.quantization,
            "serving_targets": ["jan.ai", "ollama"],
            "model_cutoff_time": model_cutoff_time.isoformat(),
            "last_processed_law": last_processed_law,
            "training_documents": training_documents,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        metadata_path = output_dir / "model_manifest.json"
        metadata_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata_path
