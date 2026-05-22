from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    pdftoppm_path = shutil.which("pdftoppm")
    if not pdftoppm_path:
        print("pdftoppm is not available on PATH.")
        return

    sample_pdf = ROOT / "tests" / "data" / "Zmluva_spravna.pdf"
    with tempfile.TemporaryDirectory(prefix="poppler-render-demo-") as temp_dir:
        output_prefix = Path(temp_dir) / "page"
        subprocess.run(
            [pdftoppm_path, "-png", "-f", "1", "-l", "1", str(sample_pdf), str(output_prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        pages = sorted(Path(temp_dir).glob("page-*.png"))
        if not pages:
            print("pdftoppm is available but did not render a page.")
            return
        print(f"Rendered {len(pages)} page(s) with pdftoppm; first PNG bytes={pages[0].stat().st_size}.")


if __name__ == "__main__":
    main()
