from __future__ import annotations

import argparse

from .config import LocalModelBuilderConfig
from .domain import LocalModelBuildRequest
from .service import LocalModelBuilderService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a local country law model bundle")
    parser.add_argument("--country", required=True, help="Country ISO code, e.g. SK")
    parser.add_argument("--laws-db", required=True, help="Path to source laws sqlite database")
    parser.add_argument("--base-model", default="meta-llama/Meta-Llama-3-13B-Instruct")
    parser.add_argument("--adapter-name", default="lora-slovak-legal")
    parser.add_argument("--quantization", default="gguf-q4_k_m")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = LocalModelBuilderConfig(laws_db_path=args.laws_db)
    service = LocalModelBuilderService.from_config(config=config)
    result = service.build_country_model(
        LocalModelBuildRequest(
            country_code=args.country.upper(),
            base_model=args.base_model,
            adapter_name=args.adapter_name,
            quantization=args.quantization,
        )
    )
    print(
        "Built",
        f"{result.model_name}:{result.model_version}",
        f"cutoff={result.model_cutoff_time.isoformat()}",
        f"last_law={result.last_processed_law}",
    )
    print(f"Bundle: {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
