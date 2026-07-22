"""Demonstrate allowlisted environment inspection without reading a real .env."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.env_config import inspect_non_secret_values


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="env-inspection-demo-") as temporary:
        sample = Path(temporary) / ".env"
        sample.write_text(
            "DB_OPTION=local\nAPI_KEY=synthetic-secret-must-stay-hidden\n",
            encoding="utf-8",
        )
        visible = inspect_non_secret_values(sample, allowed_keys={"DB_OPTION"})
        print(visible)


if __name__ == "__main__":
    main()
