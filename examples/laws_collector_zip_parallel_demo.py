from services.laws_collector.config import LawsCollectorConfig


def main() -> None:
    config = LawsCollectorConfig.from_env()
    print(
        "laws collector zip parallel config",
        {
            "country": config.country_code,
            "import_mode": config.import_mode,
            "zip_threads": config.import_zip_max_threads,
        },
    )


if __name__ == "__main__":
    main()
