"""Create a disposable CI-only case key ring; never import production keys."""

import base64
import json
import os
from pathlib import Path
import secrets


def main() -> None:
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("Requires an ephemeral GitHub-hosted runner")
    path = Path.cwd() / "runs/storage/synthetic-e2e/case-keyring.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x", encoding="utf-8") as file:
        path.chmod(0o600)
        json.dump(
            {
                "active": "synthetic-ci",
                "keys": {"synthetic-ci": base64.b64encode(secrets.token_bytes(32)).decode("ascii")},
            },
            file,
        )
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as env:
        env.write(f"CASE_ENCRYPTION_KEY_FILE={path}\n")
    print("Disposable synthetic case key ring created; value withheld.")


if __name__ == "__main__":
    main()
