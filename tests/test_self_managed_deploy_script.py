from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "Deployment" / "server" / "deploy_jurisdigta_prod.sh"
DOCUMENT_ENGINE_DOCKERFILE = REPO_ROOT / "services" / "document-engine-service" / "Dockerfile"


def test_api_and_mcp_containers_override_email_outbox_database() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    api_block = _docker_run_block(script, "--name jurisdigta-api")
    mcp_block = _docker_run_block(script, "--name jurisdigta-mcp")

    for block in (api_block, mcp_block):
        assert '--env-file "$ENV_FILE"' in block
        assert '--log-opt "max-size=$DOCKER_LOG_MAX_SIZE"' in block
        assert '--log-opt "max-file=$DOCKER_LOG_MAX_FILE"' in block
        assert '-e DB_CLOUD="$api_db_cloud"' in block
        assert "-e EMAIL_DB_OPTION=postgres" in block
        assert '-e EMAIL_DB_CLOUD="$api_db_cloud"' in block
        assert "-e EMAIL_DB_LOCAL=/workspace/runs/storage/api/sqlite/email.sqlite3" in block


def test_deploy_installs_log_retention_and_configures_monitoring() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"' in script
    assert "install_log_retention_cron" in script
    assert "cleanup_logs.sh" in script
    assert 'find "$LOG_DIR" -type f -name \'*.log\' -mtime +"$LOG_RETENTION_DAYS" -delete' in script
    assert 'python3 configure_monitoring.py --project-env "$ENV_FILE" --validate --start' in script


def test_deploy_installs_ollama_and_pulls_default_model() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'INSTALL_OLLAMA="${INSTALL_OLLAMA:-1}"' in script
    assert 'LOCAL_LLM_MODEL="${LOCAL_LLM_MODEL:-qwen3.6:27b}"' in script
    assert "install_ollama_service" in script
    assert "effective_ollama_host_bind" in script
    assert "app_docker_gateway" in script
    assert "OLLAMA_HOST_BIND must not expose Ollama on all interfaces" in script
    assert 'curl -fsSL https://ollama.com/install.sh -o "$installer"' in script
    assert "sudo install -d -m 755 /etc/systemd/system/ollama.service.d" in script
    assert "sudo tee /etc/systemd/system/ollama.service.d/jurisdigta-localhost.conf" in script
    assert "sudo systemctl daemon-reload" in script
    assert "sudo systemctl enable --now ollama" in script
    assert 'Environment="OLLAMA_HOST=$bind"' in script
    assert 'OLLAMA_HOST="$bind" ollama pull "$LOCAL_LLM_MODEL"' in script
    assert 'OLLAMA_HOST="$bind" ollama list | grep -F "$LOCAL_LLM_MODEL"' in script


def test_api_containers_receive_private_ollama_gateway_url() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    api_block = _docker_run_block(script, "--name jurisdigta-api")
    mcp_block = _docker_run_block(script, "--name jurisdigta-mcp")

    assert 'local_llm_base_url="$(local_llm_container_base_url)"' in script
    for block in (api_block, mcp_block):
        assert '-e LOCAL_LLM_BASE_URL="$local_llm_base_url"' in block
        assert '-e LOCAL_LLM_OPENAI_BASE_URL="$local_llm_base_url/v1"' in block
        assert '-e LOCAL_LLM_HEALTH_URL="$local_llm_base_url/api/tags"' in block


def test_document_engine_image_defaults_to_writable_sqlite_path() -> None:
    dockerfile = DOCUMENT_ENGINE_DOCKERFILE.read_text(encoding="utf-8")

    assert "DATABASE_URL=sqlite:////tmp/document_engine.db" in dockerfile
    assert "GENERATED_DOCUMENTS_DIR=/tmp/generated-documents" in dockerfile


def _docker_run_block(script: str, container_name_marker: str) -> str:
    start = script.index(container_name_marker)
    end = script.index("\n  docker run", start + 1)
    return script[start:end]
