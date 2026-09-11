"""Drive synthetic login through Playwright CLI without printing credentials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["login", "otp", "snapshot"])
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    user = json.loads((ROOT / "runs/storage/issue806-user.json").read_text())
    command = ["node", str(args.cli), "-s=issue806"]
    private_path: Path | None = None
    try:
        if args.step == "snapshot":
            command.append("snapshot")
        else:
            if args.step == "login":
                code = (
                    f'await page.getByRole("textbox", {{name:"Pracovný e-mail"}}).fill({json.dumps(user["email"])});'
                    f'await page.getByRole("textbox", {{name:"Heslo",exact:true}}).fill({json.dumps(user["password"])});'
                )
            else:
                code = f'await page.getByLabel("OTP kód", {{exact:true}}).fill({json.dumps(user["otp"])});'
            code += 'await page.getByRole("button", {name:"Prihlásiť sa",exact:true}).click();'
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", dir=ROOT / "runs/storage",
                                              encoding="utf-8", delete=False) as handle:
                private_path = Path(handle.name)
                handle.write("async (page) => {" + code + "}")
            command += ["run-code", "--filename", str(private_path)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=50)
        output = result.stdout + result.stderr
        for key in ("password", "otp"):
            if user.get(key):
                output = output.replace(user[key], "[REDACTED]")
        for path in (ROOT / ".playwright-cli").glob("*.yml"):
            original = path.read_text(encoding="utf-8")
            redacted = original
            for key in ("password", "otp"):
                if user.get(key):
                    redacted = redacted.replace(user[key], "[REDACTED]")
            if original != redacted:
                path.write_text(redacted, encoding="utf-8")
        print(output)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if private_path:
            private_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
