import argparse
from pathlib import Path

from .config import Settings
from .db import connect, migrate, purge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "seed-development", "purge"])
    args = parser.parse_args()
    cfg = Settings.load()
    root = next(
        (p for p in (Path.cwd(), *Path(__file__).resolve().parents) if (p / "databases/laws-tests").is_dir()),
        None,
    )
    if root is None:
        raise SystemExit("Run from the repository or release root containing databases/laws-tests")
    if args.command == "migrate":
        migrate(cfg.database_url, root)
    elif args.command == "seed-development":
        if cfg.environment == "production":
            raise SystemExit("Development seeds are forbidden in production")
        with connect(cfg.database_url) as conn:
            conn.execute((root / "databases/laws-tests/seeds/development.sql").read_text(encoding="utf-8"))
    else:
        from .identity import Identity

        identity = Identity(cfg.identity_database_url)
        with connect(cfg.database_url) as conn:
            purge(conn)
            users = conn.execute(
                "SELECT user_id FROM test_sessions UNION SELECT user_id FROM web_sessions"
            ).fetchall()
            for user in users:
                if identity.find_user_by_id(user_id=user["user_id"]) is None:
                    conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (user["user_id"],))
                    conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (user["user_id"],))
    print(f"laws-tests {args.command}: complete (values redacted)")


if __name__ == "__main__":
    main()
