"""Offline STT route example; no microphone, credentials or provider requests.

For real synthetic streaming transcription run scripts/prepare_speech_e2e.py,
then scripts/run_speech_e2e.py with the documented local services running.
"""
from pathlib import Path
import sys
import tempfile
import gc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aijurisdictionagents.api_db import ApiDatabaseStore

storage = Path(__file__).resolve().parents[1] / "runs/storage/api/sqlite"
storage.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="synthetic-stt-", dir=storage) as directory:
    root = Path(directory)
    store = ApiDatabaseStore(db_path=root / "api.sqlite3", blob_root=root / "blobs")
    store.initialize()
    user = store.create_user(email="synthetic@example.test", password="example-only", full_name="Synthetic")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic dictation")
    provider = store.upsert_ai_model_provider(provider_code="speech", provider_type="azure_speech",
        display_name="Azure Speech", region="westeurope", is_external=True, enabled=True)
    profile = store.upsert_ai_model_profile(provider_id=provider.provider_id, model_code="speech-sk",
        model_parameters={"capability": "speech_to_text", "streaming": True}, eu_data_zone_capable=True)
    store.upsert_ai_task_route_policy(task_type="speech_transcription", plan_code="free",
        preferred_external_model_profile_id=profile.model_profile_id, allow_external=True,
        require_external_ack=True, require_eu_data_zone=True)
    route = store.resolve_speech_route(user_id=user.user_id, case_id=case.case_id)
    assert route.model_profile is not None
    print("STT route:", route.model_profile.model_code, "- review and explicit Send required")
    print("No audio transcribed. Real synthetic streaming test: python scripts/run_speech_e2e.py")
    gc.collect()  # sqlite connection contexts commit; collect handles before Windows cleanup.
