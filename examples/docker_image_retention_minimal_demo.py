"""Minimal runnable verification for production Docker image retention.

Run:
    python examples/docker_image_retention_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "Deployment" / "server" / "deploy_jurisdigta_prod.sh"


def require(token: str, message: str) -> None:
    content = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}")


if __name__ == "__main__":
    require("prepare_image_rollback_candidate", "Deployments must preserve the active image.")
    require('candidate="${repository}:rollback-candidate"', "Interrupted deploys need a stable candidate tag.")
    require('previous="${repository}:previous"', "One previous version must remain tagged.")
    require(
        'for repository in "${PREPARED_IMAGE_REPOSITORIES[@]}"',
        "Only images prepared by the current deployment may be finalized.",
    )
    require("validate_health\nfinalize_image_retention", "Cleanup must run only after health validation.")
    require("docker image prune -f", "Images older than the previous version must be pruned.")
    require("docker builder prune -a -f", "Unused build cache must be pruned.")
    if "docker volume prune" in DEPLOY_SCRIPT.read_text(encoding="utf-8"):
        raise AssertionError("Image retention must never prune Docker volumes.")

    print("Docker image retention minimal demo checks passed.")
