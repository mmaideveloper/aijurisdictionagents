"""Fail-closed exact-SHA check gate; emits names/status only, never tokens."""

import argparse
import json
import os
import urllib.request


def check_runs(runs, required):
    latest = {}
    for run in runs:
        if run["name"] not in latest or run["id"] > latest[run["name"]]["id"]:
            latest[run["name"]] = run
    if not required:
        raise ValueError("Required check list must not be empty")
    for name in required:
        run = latest.get(name)
        if not run or run["status"] != "completed" or run["conclusion"] != "success":
            raise ValueError(f"Required check is not successful: {name}")
    return [latest[name]["html_url"] for name in required]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("sha")
    p.add_argument("--output", default="checks.json")
    args = p.parse_args()
    if len(args.sha) != 40 or any(c not in "0123456789abcdef" for c in args.sha):
        raise SystemExit("An immutable lowercase SHA is required")
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    required = json.loads(os.environ["LAWS_TEST_REQUIRED_CHECKS"])
    # These feature checks cannot be removed via environment configuration.
    required = list(dict.fromkeys(["laws-tests-validation", "laws-tests-real-e2e"] + required))
    runs = []
    for page in range(1, 101):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/commits/{args.sha}/check-runs?per_page=100&page={page}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        runs += data["check_runs"]
        if len(data["check_runs"]) < 100:
            break
    links = check_runs(runs, required)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"sha": args.sha, "checks": links}, handle, indent=2)
    print("All required checks succeeded for the deployment SHA.")


if __name__ == "__main__":
    main()
