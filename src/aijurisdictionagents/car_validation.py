from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
import json
from urllib.parse import quote_plus
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_VIN_ALLOWED_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_SLOVAK_SPZ_RE = re.compile(
    r"^(?:[A-Z]{2}\s?\d{3}[A-Z]{2}|[A-Z]{2}\s?[A-Z]{2}\s?\d{3}|[A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{2}[A-Z]{2}\d{3})$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class CarValidationPlan:
    mode: str
    vin: str
    spz: str
    vin_valid: bool
    vin_validation_message: str
    ownership_history_available: bool
    ownership_history_policy: str
    instructions: tuple[str, ...]
    links: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "vin": self.vin,
            "spz": self.spz,
            "vin_valid": self.vin_valid,
            "vin_validation_message": self.vin_validation_message,
            "ownership_history_available": self.ownership_history_available,
            "ownership_history_policy": self.ownership_history_policy,
            "instructions": list(self.instructions),
            "links": list(self.links),
        }


@dataclass(frozen=True)
class VehicleApiCheckResult:
    vin: str
    spz: str
    national_wanted_records: str
    vehicle_blocking: str
    leasing_status: str
    lien_status: str
    owner_count: int | None
    damage_records: tuple[dict[str, str], ...]
    vehicle_info: dict[str, str]
    source: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, object]:
        return {
            "vin": self.vin,
            "spz": self.spz,
            "national_wanted_records": self.national_wanted_records,
            "vehicle_blocking": self.vehicle_blocking,
            "leasing_status": self.leasing_status,
            "lien_status": self.lien_status,
            "owner_count": self.owner_count,
            "damage_records": list(self.damage_records),
            "vehicle_info": self.vehicle_info,
            "source": self.source,
            "raw": self.raw,
        }


class VehicleCheckApiClient:
    """Lightweight API client for Slovakia vehicle checks."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        requester: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self._requester = requester or _default_api_requester

    def check_vehicle(self, *, vin: str, spz: str = "") -> VehicleApiCheckResult:
        if not vin and not spz:
            raise ValueError("vin or spz is required for API vehicle check.")
        url = self.build_lookup_url(vin=vin, spz=spz)
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        status, content_type, response_body = self._requester(url, headers=headers)
        if status >= 400:
            raise ValueError(f"vehicle check API returned HTTP {status}")
        cleaned = response_body.strip()
        if "json" not in content_type.lower() and not cleaned.startswith("{"):
            raise ValueError("vehicle check API did not return JSON.")
        data = json.loads(cleaned) if cleaned else {}
        if not isinstance(data, dict):
            raise ValueError("vehicle check API returned invalid payload.")
        damage_records = _pick_first(data, "damage_records", "damageRecords", "damage_history", "damages", default=[])
        parsed_damage: tuple[dict[str, str], ...] = tuple(
            {
                "date": str(item.get("date", "")),
                "source": str(item.get("source", "")),
                "description": str(item.get("description", "")),
            }
            for item in damage_records
            if isinstance(item, dict)
        )
        owner_count_raw = _pick_first(
            data,
            "owner_count",
            "ownerCount",
            "numberOfOwners",
            "ownersCount",
            "pocet_majitelov",
            default=None,
        )
        owner_count = int(owner_count_raw) if str(owner_count_raw).isdigit() else None
        vehicle_info = {
            "brand": str(_pick_first(data, "brand", "make", "vehicleBrand", default="")),
            "model": str(_pick_first(data, "model", "vehicleModel", default="")),
            "year": str(_pick_first(data, "year", "modelYear", default="")),
            "color": str(_pick_first(data, "color", "vehicleColor", default="")),
        }
        return VehicleApiCheckResult(
            vin=vin,
            spz=spz,
            national_wanted_records=str(
                _pick_first(
                    data,
                    "national_wanted_records",
                    "nationalWantedRecords",
                    "wanted",
                    "isWanted",
                    "patranie",
                    default="unknown",
                )
            ),
            vehicle_blocking=str(
                _pick_first(
                    data,
                    "vehicle_blocking",
                    "vehicleBlocking",
                    "blocking",
                    "isBlocked",
                    "blokacia",
                    default="unknown",
                )
            ),
            leasing_status=str(
                _pick_first(
                    data,
                    "leasing_status",
                    "leasingStatus",
                    "leasing",
                    "isLeasing",
                    default="unknown",
                )
            ),
            lien_status=str(
                _pick_first(
                    data,
                    "lien_status",
                    "lienStatus",
                    "lien",
                    "isLien",
                    "zaloznePravo",
                    default="unknown",
                )
            ),
            owner_count=owner_count,
            damage_records=parsed_damage,
            vehicle_info=vehicle_info,
            source=str(_pick_first(data, "source", "provider", default="vehicle_check_api")),
            raw=data,
        )

    def build_lookup_url(self, *, vin: str, spz: str) -> str:
        base = self.base_url.rstrip("/")
        endpoint = base if base.endswith("/api/vehicles") else f"{base}/api/vehicles"
        params: dict[str, str] = {}
        if spz:
            params["ecv"] = spz
        if vin:
            params["vin"] = vin
        query = urlencode(params)
        return f"{endpoint}?{query}" if query else endpoint


class AICarValidatorAgent:
    """Prepare Slovakia-oriented VIN/SPZ verification plans for car checks."""

    name: str = "AICarValidatorAgent"

    _SK_TECH_CONTROL_ROOT = "https://www.stkonline.sk"
    _SK_INTERIOR_ROOT = "https://www.minv.sk"

    def build_car_validation_plan(self, *, vin: str = "", spz: str = "") -> dict[str, Any]:
        normalized_vin = self._normalize_vin(vin)
        normalized_spz = self._normalize_spz(spz)

        if not normalized_vin and not normalized_spz:
            return {
                "ok": False,
                "message": "At least one of vin or spz is required.",
            }

        vin_valid = False
        vin_message = "VIN not provided."
        if normalized_vin:
            vin_valid = self._is_valid_vin(normalized_vin)
            vin_message = "VIN format and checksum look valid." if vin_valid else "VIN has invalid format/checksum."

        instructions = [
            "Use official Slovak sources first (STK/KO and Ministry of Interior portals).",
            "Compare VIN from documents (technical certificate, insurance, contract) with provided value.",
            "Capture registration status, technical inspection validity, and mandatory insurance evidence.",
        ]

        if normalized_spz:
            instructions.append(
                f"Use SPZ/EČV {normalized_spz} to cross-check registration record and plate-to-vehicle consistency."
            )

        ownership_policy = (
            "Complete owner history is usually restricted to authorized entities (police, courts, notaries, leasing/insurer with legal basis)."
        )
        instructions.append(
            "If owner history is required, request explicit legal basis and route through authorized institution (ODI/PZ or court request)."
        )

        encoded_vin = quote_plus(normalized_vin) if normalized_vin else ""
        encoded_spz = quote_plus(normalized_spz) if normalized_spz else ""
        links: tuple[dict[str, str], ...] = (
            {
                "label": "STK online (technical checks)",
                "url": self._SK_TECH_CONTROL_ROOT,
            },
            {
                "label": "Ministry of Interior (vehicle registration info)",
                "url": self._SK_INTERIOR_ROOT,
            },
            {
                "label": "VIN quick search hint",
                "url": f"{self._SK_TECH_CONTROL_ROOT}/?q={encoded_vin}" if encoded_vin else self._SK_TECH_CONTROL_ROOT,
            },
            {
                "label": "SPZ quick search hint",
                "url": f"{self._SK_INTERIOR_ROOT}/?q={encoded_spz}" if encoded_spz else self._SK_INTERIOR_ROOT,
            },
        )

        plan = CarValidationPlan(
            mode="vin_spz" if normalized_vin and normalized_spz else ("vin" if normalized_vin else "spz"),
            vin=normalized_vin,
            spz=normalized_spz,
            vin_valid=vin_valid,
            vin_validation_message=vin_message,
            ownership_history_available=False,
            ownership_history_policy=ownership_policy,
            instructions=tuple(instructions),
            links=links,
        )

        return {
            "ok": True,
            "message": "Car validation plan prepared.",
            "query": {
                "vin": normalized_vin,
                "spz": normalized_spz,
            },
            "plan": plan.as_dict(),
        }

    @staticmethod
    def _normalize_vin(vin: str) -> str:
        return "".join(ch for ch in vin.upper().strip() if ch.isalnum())

    @staticmethod
    def _normalize_spz(spz: str) -> str:
        return " ".join(spz.upper().split())

    @staticmethod
    def _is_valid_vin(vin: str) -> bool:
        if not _VIN_ALLOWED_RE.fullmatch(vin):
            return False
        transliteration = {
            **{str(n): n for n in range(10)},
            "A": 1,
            "B": 2,
            "C": 3,
            "D": 4,
            "E": 5,
            "F": 6,
            "G": 7,
            "H": 8,
            "J": 1,
            "K": 2,
            "L": 3,
            "M": 4,
            "N": 5,
            "P": 7,
            "R": 9,
            "S": 2,
            "T": 3,
            "U": 4,
            "V": 5,
            "W": 6,
            "X": 7,
            "Y": 8,
            "Z": 9,
        }
        weights = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
        total = 0
        for idx, char in enumerate(vin):
            value = transliteration.get(char)
            if value is None:
                return False
            total += value * weights[idx]
        check_digit = "X" if total % 11 == 10 else str(total % 11)
        return vin[8] == check_digit

    def is_probable_slovak_spz(self, spz: str) -> bool:
        normalized_spz = self._normalize_spz(spz)
        if not normalized_spz:
            return False
        compact = normalized_spz.replace(" ", "")
        return bool(_SLOVAK_SPZ_RE.fullmatch(normalized_spz) or _SLOVAK_SPZ_RE.fullmatch(compact))

    def check_vehicle_via_api(
        self,
        *,
        vin: str = "",
        spz: str = "",
        client: VehicleCheckApiClient,
    ) -> dict[str, Any]:
        normalized_vin = self._normalize_vin(vin)
        normalized_spz = self._normalize_spz(spz)
        if not normalized_vin and not normalized_spz:
            return {
                "ok": False,
                "message": "At least one of vin or spz is required.",
                "result": {},
            }
        try:
            api_result = client.check_vehicle(vin=normalized_vin, spz=normalized_spz)
        except Exception as exc:  # pragma: no cover - depends on external API.
            return {
                "ok": False,
                "message": f"Vehicle API check failed: {exc}",
                "result": {},
            }
        return {
            "ok": True,
            "message": "Vehicle API check completed.",
            "result": api_result.as_dict(),
        }


def _default_api_requester(
    url: str,
    *,
    headers: dict[str, str],
) -> tuple[int, str, str]:
    request = Request(url=url, headers=headers, method="GET")
    with urlopen(request, timeout=20) as response:  # noqa: S310 - configured endpoint.
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
        payload = response.read().decode("utf-8", errors="replace")
    return status, content_type, payload


def _pick_first(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default
