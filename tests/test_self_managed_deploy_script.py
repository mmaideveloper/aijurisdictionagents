from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "Deployment" / "server" / "deploy_jurisdigta_prod.sh"


def test_api_and_mcp_containers_override_email_outbox_database() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    api_block = _docker_run_block(script, "--name jurisdigta-api")
    mcp_block = _docker_run_block(script, "--name jurisdigta-mcp")

    for block in (api_block, mcp_block):
        assert '--env-file "$ENV_FILE"' in block
        assert '-e DB_CLOUD="$api_db_cloud"' in block
        assert "-e EMAIL_DB_OPTION=postgres" in block
        assert '-e EMAIL_DB_CLOUD="$api_db_cloud"' in block
        assert "-e EMAIL_DB_LOCAL=/workspace/runs/storage/api/sqlite/email.sqlite3" in block


def _docker_run_block(script: str, container_name_marker: str) -> str:
    start = script.index(container_name_marker)
    end = script.index("\n  docker run", start + 1)
    return script[start:end]
