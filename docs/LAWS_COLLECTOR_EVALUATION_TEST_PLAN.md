# Laws Collector Evaluation Test Plan (SlovLex)

This plan validates SlovLex archive + monthly + daily incremental ingestion with GDPR and EU AI Act safeguards.

## Compliance baseline (GDPR + EU AI Act)
- Use only public legal texts from SlovLex; do not add personal data outside official source payloads.
- Keep traceable update logs and import-state metadata for accountability.
- Validate deterministic overwrite/upsert behavior to avoid inconsistent legal-risk outputs.

## Test scope mapped to requested scenarios
1. **Archive import:** verify complete archive import path and progress updates.
2. **Monthly import:** verify monthly delta import path and progress updates.
3. **Daily one-law incremental import:** verify next-law probing and progress advance based on last imported law number/date.
4. **No duplicates across daily+monthly overlap:** verify monthly re-import overwrites existing law version instead of creating duplicate document.
5. **Progress fields:** verify import state and collector progress track last processed law number/date.
6. **Embedding every 15 minutes:** verify document processor default max runtime cadence is 15 minutes and it processes unembedded records.
7. **API semantic retrieval:** verify query -> embedding -> vector similarity returns top-N records using default code constants.
8. **API fetch by record id:** verify `/v1/laws/document-text` returns the document text for a given `document_id`.

## Prepared automated tests
- `tests/test_laws_collector_zip_import.py`
  - monthly + archive flows, resume behavior, overlap safety.
- `tests/test_laws_collector.py`
  - sequential incremental planning/progress and semantic search behavior.
- `tests/test_document_processor_worker.py`
  - embedding runtime defaults (15 minutes) and startup configuration logging.
- `api/aijuristiction-api/tests/test_laws_api.py`
  - source artifact retrieval and record-id text retrieval endpoint.

## Minimal runnable example
```bash
python examples/minimal_demo.py
```

## Local validation commands
```bash
pytest tests/test_laws_collector_zip_import.py -q
pytest tests/test_laws_collector.py -q
pytest tests/test_document_processor_worker.py -q
pytest api/aijuristiction-api/tests/test_laws_api.py -q
```
