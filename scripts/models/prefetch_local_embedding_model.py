from __future__ import annotations

from aijurisdictionagents.llm import LocalEmbeddingClient, load_local_embedding_config_from_env


def main() -> int:
    config = load_local_embedding_config_from_env()
    LocalEmbeddingClient(config)
    print(
        "prefetched_local_embedding_model "
        f"model={config.model} directory={config.model_directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
