from __future__ import annotations

import pathlib
import sys


def main() -> None:
    workspace_root = pathlib.Path(__file__).resolve().parents[1]
    expected_prefix = str((workspace_root / ".conda").resolve()).lower()
    executable = sys.executable

    print(f"Workspace: {workspace_root}")
    print(f"Python executable: {executable}")

    if expected_prefix in executable.lower():
        print("OK: Running from .conda environment.")
    else:
        print("WARNING: Expected .conda environment not detected.")


if __name__ == "__main__":
    main()
