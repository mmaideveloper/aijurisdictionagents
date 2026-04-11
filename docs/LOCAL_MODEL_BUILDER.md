# LocalModelBuilder service

`LocalModelBuilder` creates a country-scoped local model bundle from an existing laws database.

## What it does

1. Reads the source `law_documents` corpus for a selected country.
2. Computes training cutoff metadata from the newest imported law.
3. Produces an Ollama/Jan-compatible bundle folder with:
   - `Modelfile`
   - `model_manifest.json`
4. Persists build metadata into `local_model_versions`, including:
   - `model_version`
   - `model_cutoff_time`
   - `last_processed_law` (for example `1234/2026`)

## Storage layout

- SQL assets: `databases/local-model-builder/migrations/`
- Runtime sqlite data: `runs/storage/local-model-builder/sqlite/`
- Model outputs: `runs/storage/local-model-builder/models/`

## CLI usage

```bash
PYTHONPATH=src python -m services.local_model_builder --country SK --laws-db ./runs/storage/laws-collector/sqlite/sk_laws.sqlite3
```

## Minimal runnable example

```bash
python examples/local_model_builder_minimal_demo.py
```

## Notes

The current implementation provides deterministic build artifacts and metadata tracking for local stack orchestration (LoRA + quantized packaging flow). You can later replace the artifact step with real fine-tuning/quantization jobs while keeping the same metadata contract.
