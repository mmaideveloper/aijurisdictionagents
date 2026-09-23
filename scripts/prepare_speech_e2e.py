"""Prepare real Slovak STT fixtures and credentials in loopback PostgreSQL only.

No customer recordings, secret output, mock routes, or fabricated transcripts.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
import wave

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TEXT = [
    "Potrebujem pripraviť návrh kúpnej zmluvy na bicykel. Dohodnutá cena je sto eur.",
    "Bicykel odovzdám kupujúcemu v pondelok. Pred podpisom si chcem celý návrh skontrolovať.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--database", default="aij_e2e_525_streaming_stt")
    parser.add_argument("--allow-non-eu-synthetic", action="store_true",
        help="Explicit test-only exception; never enables EU production acceptance")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    names = ["AIJ_AZURE_SPEECH_KEY", "AIJ_AZURE_SPEECH_REGION", "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY"]
    placeholders = {"", "unknown-variable", "your_speech_key"}
    missing = [name for name in names if os.getenv(name, "").strip() in placeholders]
    if missing:
        print("Real speech E2E pending. Missing: " + ", ".join(missing))
        return 2
    if args.check:
        print("Speech E2E configuration present; provider verification still required. Values redacted.")
        return 0
    if not args.database.startswith("aij_e2e_") or not args.database.replace("_", "").isalnum():
        raise ValueError("Only an aij_e2e_ task database is allowed")
    region = os.environ["AIJ_AZURE_SPEECH_REGION"].strip()
    non_eu_exception = region != "westeurope"
    if non_eu_exception and not args.allow_non_eu_synthetic:
        print("Real speech E2E pending: approved EU resource required; use explicit synthetic-only exception if authorized.")
        return 2
    # Known synthetic local Docker credentials; never use a production database from .env.
    database = f"postgresql://postgres:postgres@127.0.0.1:5432/{args.database}"
    assert urlsplit(database).hostname == "127.0.0.1"
    os.environ.update(DB_OPTION="postgres", DB_CLOUD=database, STORAGE_OPTION="local",
                      STORE_LOCAL=str(ROOT / "runs/storage/api/speech-e2e"))
    from aijurisdictionagents.api_db import ApiDatabaseStore
    import azure.cognitiveservices.speech as sdk

    store = ApiDatabaseStore.from_env()
    store.initialize()
    region = os.environ["AIJ_AZURE_SPEECH_REGION"].strip()
    key = os.environ["AIJ_AZURE_SPEECH_KEY"].strip()
    provider = store.upsert_ai_model_provider(provider_code="azure_speech_e2e", provider_type="azure_speech",
        display_name="Azure Speech", region=region, is_external=True, is_local=False, enabled=True)
    profile = store.upsert_ai_model_profile(provider_id=provider.provider_id, model_code="speech-sk-SK",
        model_parameters={"capability": "speech_to_text", "streaming": True, "locales": "sk-SK,en-US,de-DE"},
        # Never mark the exception resource as EU-capable.
        eu_data_zone_capable=region == "westeurope", enabled=True)
    store.upsert_ai_model_credential(provider_id=provider.provider_id,
        credential_name="speech-e2e", secret_type="api_key", secret_value=key, enabled=True)
    for plan in ("free", "case"):
        store.upsert_ai_task_route_policy(task_type="speech_transcription", plan_code=plan,
            preferred_external_model_profile_id=profile.model_profile_id, allow_external=True,
            require_external_ack=True, require_eu_data_zone=not non_eu_exception,
            fallback_local_on_error=False, fallback_local_on_budget=False, enabled=True)
    config = sdk.SpeechConfig(subscription=key, region=region)
    config.speech_synthesis_voice_name = "sk-SK-ViktoriaNeural"
    config.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)
    synth = sdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    out = ROOT / "runs/speech-e2e"
    out.mkdir(parents=True, exist_ok=True)
    # Initial silence allows the browser to establish capture; pauses produce separate utterances.
    pcm = b"\0\0" * (16000 * 2)
    for text in TEXT:
        result = synth.speak_text_async(text).get()
        if result.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            print("Synthetic fixture generation failed; provider details redacted.")
            return 2
        with wave.open(io.BytesIO(result.audio_data), "rb") as source:
            pcm += source.readframes(source.getnframes()) + b"\0\0" * (16000 * 2)
    with wave.open(str(out / "slovak-two-lines.wav"), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(pcm + b"\0\0" * (16000 * 15))
    (out / "reference.json").write_text(json.dumps({"synthetic": True, "locale": "sk-SK", "lines": TEXT,
        "provider": "azure_speech", "model": "speech-sk-SK", "region": region,
        "non_eu_synthetic_exception": non_eu_exception, "production_acceptance": "pending_eu_resource",
        "retention": "Delete fixture and test evidence within 7 days; regenerate from this script."}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared synthetic two-utterance WAV and real STT routing in the task database. Values redacted.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Provider exceptions may contain credentials; expose only a failure class.
        print(f"Speech E2E preparation failed ({type(exc).__name__}); no secrets displayed.")
        sys.exit(2)
