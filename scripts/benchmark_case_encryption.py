"""Synthetic PostgreSQL retrieval microbenchmark; excludes embedding/model latency.

Replays identical vectors and text through the database, parser and ranking
functions. Plaintext baseline data belongs to a temporary synthetic account and
is removed in finally. Never run against a non-loopback database.
"""
from __future__ import annotations

import json
import random
import statistics
import time
from urllib.parse import urlparse
from uuid import uuid4

from run_issue922_e2e import configure, OUTPUT


def main() -> None:
    configure()
    from aijurisdictionagents.api_db import ApiDatabaseStore
    from aijurisdictionagents.api_db.store import CaseDocumentChunk
    from aijurisdictionagents.case_exports import now
    from aijurisdictionagents.privacy_retention import purge_case, cleanup_files
    from services.document_processor.runtime import cosine_similarity, parse_embedding_vector
    secured = ApiDatabaseStore.from_env()
    if urlparse(secured.db_cloud).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Loopback synthetic database required")
    baseline = ApiDatabaseStore(db_path=secured.db_path, blob_root=secured.blob_root,
                               db_option=secured.db_option, db_cloud=secured.db_cloud)
    baseline.case_cipher = None  # Explicit isolated synthetic baseline, never runtime fallback.
    run_id = "issue922-benchmark-" + uuid4().hex
    user = secured.create_user(email=run_id + "@example.invalid", password="Synthetic benchmark only")
    cases = []
    rng = random.Random(922)
    vectors = [[rng.uniform(-1, 1) for _ in range(384)] for _ in range(100)]
    query = vectors[17]
    timings = {"plaintext": [], "encrypted": []}
    matches = []
    try:
        for store in (baseline, secured):
            case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic retrieval benchmark")
            cases.append((store, case.case_id))
            doc = store.add_case_document(case_id=case.case_id, kind="uploaded", version=1, original_filename="synthetic.txt", payload=b"Synthetic benchmark only")
            timestamp = now()
            chunks = [CaseDocumentChunk(chunk_id=str(uuid4()), doc_id=doc, case_id=case.case_id,
                      chunk_index=i, chunk_text=f"Synthetic paragraph {i}: loan repayment evidence. " * 12,
                      embedding_vector=json.dumps(vector), embedding_model="replayed-synthetic-384", embedding_dimensions=384,
                      start_offset=i * 500, end_offset=(i + 1) * 500, created_at=timestamp, updated_at=timestamp)
                      for i, vector in enumerate(vectors)]
            store.replace_document_chunks(doc_id=doc, case_id=case.case_id, chunks=chunks)
        for iteration in range(45):
            rankings = []
            for index in ([0, 1] if iteration % 2 else [1, 0]):
                store, case_id = cases[index]
                start = time.perf_counter()
                entries = store.list_case_document_chunks(case_id=case_id)
                ranked = sorted(entries, key=lambda chunk: cosine_similarity(query, parse_embedding_vector(chunk.embedding_vector)), reverse=True)
                elapsed = (time.perf_counter() - start) * 1000
                if iteration >= 5:
                    timings["plaintext" if index == 0 else "encrypted"].append(elapsed)
                rankings.append([chunk.chunk_index for chunk in ranked[:5]])
            matches.append(rankings[0] == rankings[1])
        p95 = {key: statistics.quantiles(values, n=100, method="inclusive")[94] for key, values in timings.items()}
        result = {"runId": run_id, "syntheticOnly": True, "database": "loopback PostgreSQL issue922",
                  "chunks": 100, "vectorDimensions": 384, "measuredIterations": 40,
                  "top5Identical": all(matches), "p95Milliseconds": p95,
                  "p95OverheadPercent": (p95["encrypted"] / p95["plaintext"] - 1) * 100,
                  "scope": "database read, decryption, vector parsing and cosine ranking; excludes embedding generation and model calls"}
        (OUTPUT / "retrieval-benchmark.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        for store, case_id in cases:
            purge_case(store, case_id, user.user_id)
        cleanup_files(secured)
        with secured._connect() as conn:
            secured._execute(conn, "DELETE FROM users WHERE user_id = ?", (user.user_id,))


if __name__ == "__main__":
    main()
