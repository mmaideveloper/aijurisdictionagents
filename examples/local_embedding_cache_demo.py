from __future__ import annotations

from aijurisdictionagents.llm import load_local_embedding_config_from_env


def main() -> int:
    config = load_local_embedding_config_from_env()
    print(f"model: {config.model}")
    print(f"directory: {config.model_directory}")
    print(f"cached: {(config.model_directory / 'modules.json').exists()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
