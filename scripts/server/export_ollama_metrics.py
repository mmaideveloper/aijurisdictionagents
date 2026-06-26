from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> None:
    args = _parse_args()
    server = ThreadingHTTPServer((args.host, args.port), _handler(args))
    print(f"serving Ollama Prometheus metrics on http://{args.host}:{args.port}/metrics")
    server.serve_forever()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expose Ollama runtime data as Prometheus text metrics.")
    parser.add_argument("--host", default=os.getenv("OLLAMA_METRICS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OLLAMA_METRICS_PORT", "9109")))
    parser.add_argument("--ollama-url", default=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("OLLAMA_METRICS_TIMEOUT", "5")))
    return parser.parse_args()


def _handler(args: argparse.Namespace) -> type[BaseHTTPRequestHandler]:
    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/metrics", "/"):
                self.send_error(404)
                return
            body = _render_ollama_metrics(base_url=args.ollama_url, timeout=args.timeout)
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return MetricsHandler


def _render_ollama_metrics(*, base_url: str, timeout: float) -> str:
    normalized_base = base_url.rstrip("/")
    lines: list[str] = []
    _append_help(lines, "jurisdigta_ollama_up", "Whether the Ollama API responded to exporter probes.", "gauge")
    try:
        tags, tags_duration = _fetch_json(f"{normalized_base}/api/tags", timeout=timeout)
        ps, ps_duration = _fetch_json(f"{normalized_base}/api/ps", timeout=timeout)
    except Exception as exc:
        lines.append(f'jurisdigta_ollama_up{{error="{_label(str(exc))}"}} 0')
        lines.append("")
        return "\n".join(lines)

    lines.append('jurisdigta_ollama_up{error=""} 1')
    _append_help(lines, "jurisdigta_ollama_probe_duration_seconds", "Ollama exporter probe duration by endpoint.", "gauge")
    lines.append(f'jurisdigta_ollama_probe_duration_seconds{{endpoint="/api/tags"}} {tags_duration}')
    lines.append(f'jurisdigta_ollama_probe_duration_seconds{{endpoint="/api/ps"}} {ps_duration}')

    configured_model = os.getenv("LOCAL_LLM_MODEL", "").strip()
    loaded_models = _models(tags)
    running_models = _models(ps)
    running_names = {str(model.get("name") or model.get("model") or "") for model in running_models}

    _append_help(lines, "jurisdigta_ollama_models_total", "Installed Ollama model count.", "gauge")
    lines.append(f"jurisdigta_ollama_models_total {len(loaded_models)}")
    _append_help(lines, "jurisdigta_ollama_running_models_total", "Currently loaded/running Ollama model count.", "gauge")
    lines.append(f"jurisdigta_ollama_running_models_total {len(running_models)}")
    _append_help(lines, "jurisdigta_ollama_configured_model_present", "Whether LOCAL_LLM_MODEL exists in Ollama inventory.", "gauge")
    model_names = {str(model.get("name") or model.get("model") or "") for model in loaded_models}
    present = 1 if configured_model and configured_model in model_names else 0
    lines.append(f'jurisdigta_ollama_configured_model_present{{model="{_label(configured_model)}"}} {present}')

    _append_help(lines, "jurisdigta_ollama_model_size_bytes", "Installed Ollama model size in bytes.", "gauge")
    _append_help(lines, "jurisdigta_ollama_model_modified_timestamp_seconds", "Installed Ollama model modified timestamp.", "gauge")
    _append_help(lines, "jurisdigta_ollama_model_loaded", "Whether an installed Ollama model is currently loaded.", "gauge")
    for model in loaded_models:
        name = str(model.get("name") or model.get("model") or "")
        details = model.get("details") if isinstance(model.get("details"), dict) else {}
        labels = (
            f'model="{_label(name)}",'
            f'family="{_label(str(details.get("family") or ""))}",'
            f'parameter_size="{_label(str(details.get("parameter_size") or ""))}",'
            f'quantization="{_label(str(details.get("quantization_level") or ""))}"'
        )
        lines.append(f"jurisdigta_ollama_model_size_bytes{{{labels}}} {_number(model.get('size'), 0)}")
        modified = _timestamp(model.get("modified_at"))
        if modified is not None:
            lines.append(f"jurisdigta_ollama_model_modified_timestamp_seconds{{{labels}}} {modified}")
        lines.append(f"jurisdigta_ollama_model_loaded{{{labels}}} {1 if name in running_names else 0}")

    _append_help(lines, "jurisdigta_ollama_running_model_size_bytes", "Loaded Ollama model size in bytes.", "gauge")
    _append_help(lines, "jurisdigta_ollama_running_model_vram_bytes", "Loaded Ollama model VRAM size in bytes.", "gauge")
    _append_help(lines, "jurisdigta_ollama_running_model_expires_timestamp_seconds", "Unix timestamp when Ollama plans to unload the model.", "gauge")
    for model in running_models:
        name = str(model.get("name") or model.get("model") or "")
        labels = f'model="{_label(name)}",processor="{_label(str(model.get("processor") or ""))}"'
        lines.append(f"jurisdigta_ollama_running_model_size_bytes{{{labels}}} {_number(model.get('size'), 0)}")
        lines.append(f"jurisdigta_ollama_running_model_vram_bytes{{{labels}}} {_number(model.get('size_vram'), 0)}")
        expires_at = _timestamp(model.get("expires_at"))
        if expires_at is not None:
            lines.append(f"jurisdigta_ollama_running_model_expires_timestamp_seconds{{{labels}}} {expires_at}")

    lines.append("")
    return "\n".join(lines)


def _fetch_json(url: str, *, timeout: float) -> tuple[dict[str, Any], float]:
    started = datetime.now(timezone.utc)
    request = Request(url)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"{url}: {exc.reason}") from exc
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url}: response was not a JSON object")
    return payload, duration


def _models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("models")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _append_help(lines: list[str], name: str, help_text: str, metric_type: str) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type}")


def _timestamp(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def _number(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


if __name__ == "__main__":
    main()
