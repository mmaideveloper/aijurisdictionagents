from __future__ import annotations

import pathlib
import sys


def main() -> None:
    workspace_root = pathlib.Path(__file__).resolve().parents[1]
    expected_prefixes = [
        str((workspace_root / "conda").absolute()).lower(),
        str((workspace_root / ".conda").absolute()).lower(),
    ]
    executable = sys.executable

    print(f"Workspace: {workspace_root}")
    print(f"Python executable: {executable}")

    if any(prefix in executable.lower() for prefix in expected_prefixes):
        print("OK: Running from repo-local conda environment.")
    else:
        print("WARNING: Expected repo-local conda environment not detected.")


if __name__ == "__main__":
    main()
