from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import re
from threading import Lock
from uuid import uuid4

import httpx


_MODEL_NAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)


@dataclass(frozen=True)
class OllamaInstalledModel:
    name: str
    model: str
    modified_at: str
    size: int
    digest: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class OllamaModelJob:
    job_id: str
    action: str
    model: str
    status: str
    message: str
    created_at: str
    updated_at: str


class OllamaAdminService:
    def __init__(self, *, base_url: str | None = None, timeout_seconds: float = 120.0) -> None:
        raw_base_url = (base_url or os.getenv("LOCAL_LLM_BASE_URL") or "").strip()
        if not raw_base_url or raw_base_url.lower() == "unknown-variable":
            raw_base_url = "http://127.0.0.1:11434"
        if raw_base_url.rstrip("/").endswith("/v1"):
            raw_base_url = raw_base_url.rstrip("/")[:-3]
        self.base_url = raw_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def list_models(self) -> list[OllamaInstalledModel]:
        payload = self._request("GET", "/api/tags").json()
        models = payload.get("models", [])
        if not isinstance(models, list):
            return []
        return [_model_from_payload(item) for item in models if isinstance(item, dict)]

    def list_running_model_names(self) -> set[str]:
        try:
            payload = self._request("GET", "/api/ps").json()
        except httpx.HTTPError:
            return set()
        models = payload.get("models", [])
        if not isinstance(models, list):
            return set()
        names: set[str] = set()
        for item in models:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name") or item.get("model")
            if isinstance(raw_name, str) and raw_name.strip():
                names.add(raw_name.strip())
        return names

    def pull_model(self, model: str) -> str:
        normalized = validate_ollama_registry_model_name(model)
        self._request("POST", "/api/pull", json={"model": normalized, "stream": False})
        return normalized

    def remove_model(self, model: str) -> str:
        normalized = validate_ollama_registry_model_name(model)
        self._request("DELETE", "/api/delete", json={"model": normalized})
        return normalized

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.request(method, path, json=json)
        response.raise_for_status()
        return response


class OllamaModelJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, OllamaModelJob] = {}
        self._lock = Lock()

    def start(self, *, action: str, model: str) -> OllamaModelJob:
        now = _now_iso()
        job = OllamaModelJob(
            job_id=str(uuid4()),
            action=action,
            model=model,
            status="queued",
            message="Queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> OllamaModelJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def run(self, *, job_id: str, operation: str, model: str, service: OllamaAdminService) -> None:
        self._update(job_id=job_id, status="running", message="Running")
        try:
            if operation == "pull":
                service.pull_model(model)
            elif operation == "remove":
                service.remove_model(model)
            else:
                raise ValueError(f"Unsupported Ollama model operation: {operation}")
        except Exception as exc:  # pragma: no cover - exact client exception type depends on transport.
            self._update(job_id=job_id, status="failed", message=str(exc))
            return
        self._update(job_id=job_id, status="succeeded", message="Completed")

    def _update(self, *, job_id: str, status: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.message = message
            job.updated_at = _now_iso()


def validate_ollama_registry_model_name(value: str) -> str:
    model = value.strip()
    if (
        not model
        or len(model) > 160
        or model.startswith("-")
        or "://" in model
        or "\\" in model
        or ".." in model
        or "//" in model
        or any(char.isspace() for char in model)
        or not _MODEL_NAME_RE.fullmatch(model)
    ):
        raise ValueError("Model must be an Ollama registry tag such as qwen3.6:27b")
    namespace = model.split("/", 1)[0]
    if "/" in model and "." in namespace:
        raise ValueError("Model must come from the Ollama registry, not an external host")
    return model


def _model_from_payload(payload: dict[str, object]) -> OllamaInstalledModel:
    raw_name = payload.get("name") or payload.get("model") or ""
    raw_model = payload.get("model") or raw_name
    raw_details = payload.get("details")
    return OllamaInstalledModel(
        name=str(raw_name),
        model=str(raw_model),
        modified_at=str(payload.get("modified_at") or ""),
        size=_int_value(payload.get("size")),
        digest=str(payload.get("digest") or ""),
        details=raw_details if isinstance(raw_details, dict) else {},
    )


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
