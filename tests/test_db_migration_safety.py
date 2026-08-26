from __future__ import annotations

import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SQL_ROOTS = (
    _REPO_ROOT / "databases" / "api",
    _REPO_ROOT / "databases" / "laws-collector",
)
_FORBIDDEN_PATTERNS = (
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE), "DROP COLUMN"),
    (re.compile(r"\bDROP\s+CONSTRAINT\b", re.IGNORECASE), "DROP CONSTRAINT"),
    (re.compile(r"\bRENAME\s+COLUMN\b", re.IGNORECASE), "RENAME COLUMN"),
    (re.compile(r"\bALTER\s+TABLE\b[\s\S]*?\bRENAME\s+TO\b", re.IGNORECASE), "RENAME TABLE"),
    (re.compile(r"\bALTER\s+COLUMN\b[\s\S]*?\bTYPE\b", re.IGNORECASE), "ALTER COLUMN TYPE"),
    (re.compile(r"\bALTER\s+COLUMN\b[\s\S]*?\bSET\s+NOT\s+NULL\b", re.IGNORECASE), "SET NOT NULL"),
)
_LEGACY_ALLOWED_EXCEPTIONS = {
    Path("databases/laws-collector/migrations/0003_enable_real_law_embeddings.sql"): {
        "ALTER COLUMN TYPE"
    },
    Path("databases/api/migrations/0019_document_templates_case_catalog.sql"): {
        "DROP CONSTRAINT"
    },
}


def _strip_sql_comments(sql: str) -> str:
    without_block_comments = re.sub(r"/\*[\s\S]*?\*/", "", sql)
    return re.sub(r"--.*?$", "", without_block_comments, flags=re.MULTILINE)


def test_sql_migrations_remain_backward_compatible() -> None:
    migration_files = sorted(
        path
        for root in _SQL_ROOTS
        for path in root.rglob("*.sql")
        if path.is_file()
    )
    assert migration_files, "Expected SQL migration files to exist."

    failures: list[str] = []
    for path in migration_files:
        relative_path = path.relative_to(_REPO_ROOT)
        allowed_labels = _LEGACY_ALLOWED_EXCEPTIONS.get(relative_path, set())
        sql = _strip_sql_comments(path.read_text(encoding="utf-8"))
        for pattern, label in _FORBIDDEN_PATTERNS:
            if label in allowed_labels:
                continue
            if pattern.search(sql):
                failures.append(f"{relative_path} contains forbidden operation: {label}")

    assert not failures, "Database migrations must remain backward-compatible:\n" + "\n".join(failures)
