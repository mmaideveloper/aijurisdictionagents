from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

def main() -> int:
    from aijurisdictionagents.llm import (
        LocalEmbeddingClient,
        load_local_embedding_config_from_env,
    )

    config = load_local_embedding_config_from_env()
    LocalEmbeddingClient(config)
    print(
        "prefetched_local_embedding_model "
        f"model={config.model} directory={config.model_directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
