"""Print the minimal command for the Playwright payment-process E2E.

Run from the repository root:

    python examples/payment_process_e2e_demo.py
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    e2e_dir = repo_root / "api" / "aijuristiction-api" / "e2e-playwright"
    spec = e2e_dir / "tests" / "payment-process.spec.ts"
    if not spec.exists():
        raise SystemExit(f"Missing payment E2E spec: {spec}")

    print("Payment-process E2E minimal command:")
    print(f"cd {e2e_dir}")
    print("npm run test:payment")


if __name__ == "__main__":
    main()
