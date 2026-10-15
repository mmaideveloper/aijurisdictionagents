"""Verify the real embedding import without downloading or loading model weights."""
from importlib.metadata import version

from sentence_transformers import SentenceTransformer


def main() -> None:
    assert callable(SentenceTransformer)
    for package in ("torch", "sentence-transformers", "transformers"):
        print(f"{package}={version(package)}")
    print("Embedding import passed; no model weights or user data were loaded.")


if __name__ == "__main__":
    main()
