"""Deterministic synthetic demo: python examples/privacy_controls_demo.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import gc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aijurisdictionagents.api_db import ApiDatabaseStore  # noqa: E402
from aijurisdictionagents.privacy import (  # noqa: E402
    CONSENT_VERSION, PrivacyControls, PrivacyDenied, transparency,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "runs/storage/privacy-demo"
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root) as directory:
        store = ApiDatabaseStore(db_path=Path(directory) / "sqlite/demo.db", blob_root=Path(directory) / "files")
        store.initialize()
        user = store.create_user(email="privacy-demo@example.test", password="synthetic-only", full_name="Synthetic demo")
        controls = PrivacyControls(store)
        for grant in (False, True, False):
            controls.consent(user.user_id, "external_models", grant, version=CONSENT_VERSION)
            try:
                controls.require_processing(user.user_id, "external_models")
                print("External models: allowed")
            except PrivacyDenied:
                print("External models: blocked")
        print(transparency("synthetic-demo", "offline-example"))
        request = controls.request_erasure(user.user_id, "delete")
        print("Erasure:", controls.review_erasure(request, True))
        gc.collect()


if __name__ == "__main__":
    main()
