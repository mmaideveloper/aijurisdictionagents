"""Reuse the real #864 audit fixture against isolated #206 PostgreSQL databases.

Run --prepare, --services (separate terminal), then --authenticate. The existing
fixture owns the ignored runs/e2e/issue864 manifest/auth paths in THIS worktree.
No model, database response, authentication result or browser state is fabricated.
"""

import argparse
import sys

import prepare_issue_864_langgraph_audit_e2e as fixture
import run_issue_864_e2e_services as services


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--setup", action="store_true")
    actions.add_argument("--services", action="store_true")
    actions.add_argument("--authenticate", action="store_true")
    args = parser.parse_args()
    # Synthetic local database configuration, never production credentials.
    fixture.API_DATABASE_URL = services.API_DATABASE_URL = (
        "postgresql://postgres:postgres@127.0.0.1:5432/juris_audit_e2e_206"
    )
    fixture.LAWS_DATABASE_URL = services.LAWS_DATABASE_URL = (
        "postgresql://postgres:postgres@127.0.0.1:5432/juris_audit_laws_e2e_206"
    )
    if args.setup:
        return fixture.setup()
    if args.services:
        sys.argv = [sys.argv[0]]
        return services.main()
    if args.authenticate:
        return fixture.authenticate()
    return fixture.main()


if __name__ == "__main__":
    raise SystemExit(main())
