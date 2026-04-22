from __future__ import annotations

import re

from .registry import ToolRegistry, build_default_tool_registry

_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", flags=re.IGNORECASE)
_SPZ_RE = re.compile(r"\b([A-Z]{2}\s?\d{3}[A-Z]{2}|[A-Z]{2}\s?[A-Z]{2}\s?\d{3})\b", flags=re.IGNORECASE)
_CAR_MARKERS = (
    "auto",
    "vozid",
    "car",
    "vin",
    "spz",
    "ečv",
    "ecv",
)


def answer_slovak_car_validation_question(
    user_question: str,
    *,
    registry: ToolRegistry | None = None,
) -> str | None:
    normalized = " ".join(user_question.strip().split())
    if not normalized:
        return None

    lowered = normalized.lower()
    if not any(marker in lowered for marker in _CAR_MARKERS):
        return None

    vin_match = _VIN_RE.search(normalized)
    spz_match = _SPZ_RE.search(normalized)
    vin = vin_match.group(1).upper() if vin_match else ""
    spz = spz_match.group(1).upper() if spz_match else ""

    runtime_registry = registry or build_default_tool_registry()
    if not runtime_registry.has_tool("slovakia_car_validate"):
        return "Nástroj slovakia_car_validate nie je dostupný."

    result = runtime_registry.run("slovakia_car_validate", vin=vin, spz=spz)
    if not result.ok:
        return f"Overenie vozidla zlyhalo: {result.message}"

    if not result.records:
        return "Overenie vozidla nevrátilo žiadne údaje."

    first = result.records[0]
    plan = first.get("plan", {})
    api_check = first.get("api_check", {})
    api_result = api_check.get("result", {}) if isinstance(api_check, dict) else {}
    vin_status = str(plan.get("vin_validation_message", "VIN nebol poskytnutý."))
    ownership_policy = str(plan.get("ownership_history_policy", ""))
    spz_flag = "áno" if first.get("spz_probable_slovak") else "nie"
    api_message = str(api_check.get("message", ""))
    national_wanted = str(api_result.get("national_wanted_records", "unknown"))
    vehicle_blocking = str(api_result.get("vehicle_blocking", "unknown"))
    leasing_status = str(api_result.get("leasing_status", "unknown"))
    lien_status = str(api_result.get("lien_status", "unknown"))
    owner_count = api_result.get("owner_count", None)
    damage_count = len(api_result.get("damage_records", [])) if isinstance(api_result.get("damage_records"), list) else 0
    vehicle_info = api_result.get("vehicle_info", {}) if isinstance(api_result.get("vehicle_info"), dict) else {}
    vehicle_short = " ".join(
        part
        for part in (
            str(vehicle_info.get("brand", "")).strip(),
            str(vehicle_info.get("model", "")).strip(),
            str(vehicle_info.get("year", "")).strip(),
        )
        if part
    ) or "neznáme"

    return (
        f"Predbežné overenie vozidla je pripravené. VIN: {first.get('vin') or 'neuvedené'} ({vin_status}) | "
        f"SPZ: {first.get('spz') or 'neuvedené'} (slovenský formát: {spz_flag}). "
        f"API: {api_message} | Pátranie: {national_wanted}, blokácia: {vehicle_blocking}, "
        f"leasing: {leasing_status}, záložné právo: {lien_status}, počet majiteľov: {owner_count if owner_count is not None else 'neznáme'}, "
        f"záznamy poškodenia: {damage_count}, vozidlo: {vehicle_short}. História vlastníkov: {ownership_policy}"
    )
