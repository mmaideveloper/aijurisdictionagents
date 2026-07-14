#!/usr/bin/env python3
"""Profile-aware environment audit/bootstrap/merge; output is always value-redacted."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

UNKNOWN = "unknown-variable"
ACTIVE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
EXAMPLE_RE = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
UNSAFE = (
    "unknown-variable",
    "your_",
    "your-",
    "changeit",
    "replace-with",
    "optional_",
    "<",
    ">",
    "$(",
    "instrumentationkey=",
)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse(path: Path, example: bool = False) -> tuple[dict[str, str], list[str], list[int]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    malformed: list[int] = []
    if not path.exists():
        return values, duplicates, malformed
    matcher = EXAMPLE_RE if example else ACTIVE_RE
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or (not example and line.lstrip().startswith("#")):
            continue
        match = matcher.match(line)
        if not match:
            if not example:
                malformed.append(number)
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in values:
            duplicates.append(key)
        else:
            values[key] = value
    return values, sorted(set(duplicates)), malformed


def profiles(path: Path) -> dict[str, dict[str, set[str]]]:
    definitions = json.loads(path.read_text(encoding="utf-8"))["profiles"]
    result: dict[str, dict[str, set[str]]] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> dict[str, set[str]]:
        if name in result:
            return result[name]
        if name in stack:
            raise ValueError("Circular environment profile inheritance")
        definition = definitions[name]
        required = set(definition.get("required", []))
        optional = set(definition.get("optional", []))
        for parent in definition.get("extends", []):
            inherited = resolve(parent, stack + (name,))
            required.update(inherited["required"])
            optional.update(inherited["optional"])
        optional.difference_update(required)
        result[name] = {"required": required, "optional": optional}
        return result[name]

    for name in definitions:
        resolve(name)
    return result


def safe(value: str) -> bool:
    lower = value.strip().lower()
    return bool(lower) and not any(marker in lower for marker in UNSAFE)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if os.name != "nt":
            os.chmod(temporary_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def audit(env_path: Path, example_path: Path, profile: dict[str, set[str]]) -> dict[str, object]:
    values, duplicates, malformed = parse(env_path)
    schema, _, _ = parse(example_path, example=True)
    required = set(profile["required"])
    alternatives: list[list[str]] = []
    if values.get("LLM_PROVIDER", "").lower() == "azurefoundry":
        required.update(
            {
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_OPENAI_API_VERSION",
                "AZURE_OPENAI_EMBEDDINGS_MODEL",
            }
        )
        if not any(
            values.get(key, "").strip() not in {"", UNKNOWN}
            for key in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_AD_TOKEN")
        ):
            alternatives.append(["AZURE_OPENAI_AD_TOKEN", "AZURE_OPENAI_API_KEY"])
    missing = sorted(required - values.keys())
    unresolved = sorted(key for key in required & values.keys() if values[key] in {"", UNKNOWN})
    optional_unknown = sorted(
        key for key, value in values.items() if key not in required and value in {"", UNKNOWN}
    )
    blocking = bool(missing or unresolved or alternatives or duplicates or malformed)
    return {
        "profile_ready": not blocking,
        "missing_required": missing,
        "unresolved_required": unresolved,
        "missing_one_of": alternatives,
        "unknown_optional": optional_unknown,
        "duplicate_keys": duplicates,
        "malformed_line_numbers": malformed,
        "extra_keys": sorted(values.keys() - schema.keys()),
        "configured_key_count": len(values),
        "schema_key_count": len(schema),
    }


def bootstrap(
    env_path: Path, example_path: Path, selected_keys: set[str] | None = None
) -> dict[str, list[str]]:
    schema, _, _ = parse(example_path, example=True)
    existing, _, _ = parse(env_path)
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    repaired: list[str] = []
    for index, line in enumerate(lines):
        match = ACTIVE_RE.match(line)
        if match and match.group(2).strip() == UNKNOWN and safe(schema.get(match.group(1), "")):
            lines[index] = f"{match.group(1)}={schema[match.group(1)]}"
            repaired.append(match.group(1))
    added: list[str] = []
    for key, default in schema.items():
        if selected_keys is not None and key not in selected_keys:
            continue
        if key not in existing:
            lines.append(f"{key}={default if safe(default) else UNKNOWN}")
            added.append(key)
    atomic_write(env_path, "\n".join(lines).rstrip() + "\n")
    return {"added": sorted(added), "repaired": sorted(repaired)}


def merge(env_path: Path, source_path: Path) -> dict[str, list[str]]:
    source, duplicates, malformed = parse(source_path)
    if not source or duplicates or malformed:
        raise ValueError("Authoritative profile is empty, duplicated, or malformed")
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    updated: list[str] = []
    for index, line in enumerate(lines):
        match = ACTIVE_RE.match(line)
        if match:
            key = match.group(1)
            seen.add(key)
            if key in source:
                lines[index] = f"{key}={source[key]}"
                updated.append(key)
    added = sorted(source.keys() - seen)
    lines.extend(f"{key}={source[key]}" for key in added)
    atomic_write(env_path, "\n".join(lines).rstrip() + "\n")
    return {"added": added, "updated": sorted(updated)}


def names(label: str, values: list[object]) -> str:
    return f"{label}: {', '.join(map(str, values)) if values else 'none'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=root() / "config/env_profiles.json")
    parser.add_argument("--example", type=Path, default=root() / ".env.example")
    parser.add_argument("--env-file", type=Path, default=root() / ".env")
    parser.add_argument("--profile", default="local-core")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("audit")
    check.add_argument("--json", action="store_true")
    check.add_argument("--strict", action="store_true")
    commands.add_parser("bootstrap")
    combine = commands.add_parser("merge")
    combine.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    selected = profiles(args.profiles)
    if args.profile not in selected:
        print(f"Unknown environment profile: {args.profile}", file=sys.stderr)
        return 2
    if args.command == "bootstrap":
        selected_keys = selected[args.profile]["required"] | selected[args.profile]["optional"]
        result = bootstrap(args.env_file, args.example, selected_keys)
        print(names("Added keys", result["added"]))
        print(names("Repaired keys", result["repaired"]))
        print("Values are redacted.")
        return 0
    if args.command == "merge":
        result = merge(args.env_file, args.source)
        print(names("Added keys", result["added"]))
        print(names("Updated keys", result["updated"]))
        print("Values are redacted.")
        return 0
    result = audit(args.env_file, args.example, selected[args.profile])
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Profile {args.profile}: {'READY' if result['profile_ready'] else 'BLOCKED'}")
        for label, key in (
            ("Missing", "missing_required"),
            ("Unresolved", "unresolved_required"),
            ("Optional unresolved", "unknown_optional"),
            ("Duplicates", "duplicate_keys"),
            ("Extra", "extra_keys"),
        ):
            print(names(label, result[key]))
        for alternatives in result["missing_one_of"]:
            print(names("One of required", alternatives))
        print(names("Malformed lines", result["malformed_line_numbers"]))
        print("Values are redacted.")
    return 1 if args.strict and not result["profile_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
