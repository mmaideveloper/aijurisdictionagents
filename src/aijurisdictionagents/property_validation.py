from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class LVSearchPlan:
    mode: str
    search_scope: str
    primary_provider: str
    fallback_providers: tuple[str, ...]
    instructions: tuple[str, ...]
    links: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "search_scope": self.search_scope,
            "primary_provider": self.primary_provider,
            "fallback_providers": list(self.fallback_providers),
            "instructions": list(self.instructions),
            "links": list(self.links),
        }


class AIPropertyValidatorAgent:
    """Prepare Slovak LV lookup/download plans for person-name and LV-number queries."""

    name: str = "AIPropertyValidatorAgent"

    _ESKN_ROOT = "https://kataster.skgeodesy.sk/eskn-portal"
    _CICA_ROOT = "https://cica.vugk.sk"

    def build_lv_lookup_plan(
        self,
        *,
        person_name: str = "",
        lv_number: str = "",
        cadastral_unit: str = "",
        municipality: str = "",
    ) -> dict[str, object]:
        normalized_person_name = " ".join(person_name.strip().split())
        normalized_lv_number = "".join(ch for ch in lv_number.strip() if ch.isdigit())
        normalized_cadastral_unit = " ".join(cadastral_unit.strip().split())
        normalized_municipality = " ".join(municipality.strip().split())

        if not normalized_person_name and not normalized_lv_number:
            return {
                "ok": False,
                "message": "Either person_name or lv_number is required.",
            }

        if normalized_lv_number:
            plan = self._build_lv_number_plan(
                lv_number=normalized_lv_number,
                cadastral_unit=normalized_cadastral_unit,
                municipality=normalized_municipality,
            )
            return {
                "ok": True,
                "message": "LV number search plan prepared.",
                "query": {
                    "person_name": normalized_person_name,
                    "lv_number": normalized_lv_number,
                    "cadastral_unit": normalized_cadastral_unit,
                    "municipality": normalized_municipality,
                },
                "plan": plan.as_dict(),
            }

        plan = self._build_person_name_plan(person_name=normalized_person_name)
        return {
            "ok": True,
            "message": "Person-name LV search plan prepared.",
            "query": {
                "person_name": normalized_person_name,
                "lv_number": normalized_lv_number,
                "cadastral_unit": normalized_cadastral_unit,
                "municipality": normalized_municipality,
            },
            "plan": plan.as_dict(),
        }

    def _build_lv_number_plan(
        self,
        *,
        lv_number: str,
        cadastral_unit: str,
        municipality: str,
    ) -> LVSearchPlan:
        unit_hint = cadastral_unit or municipality
        instructions = [
            "Open ESKN portal and choose list vlastníctva search.",
            f"Enter LV number {lv_number}.",
            "Download informatívny výpis as PDF/HTML from the result detail page.",
        ]
        if unit_hint:
            instructions.insert(2, f"Use cadastral hint '{unit_hint}' to narrow down the result.")
        else:
            instructions.insert(
                2,
                "If cadastral unit is unknown, first identify the unit in CICA via parcel/owner navigation.",
            )

        encoded = quote_plus(lv_number)
        links = (
            {
                "label": "ESKN portal (primary)",
                "url": f"{self._ESKN_ROOT}/uplny-zoznam",
            },
            {
                "label": "CICA portal (fallback)",
                "url": self._CICA_ROOT,
            },
            {
                "label": "Quick LV keyword on ESKN",
                "url": f"{self._ESKN_ROOT}/uplny-zoznam?q={encoded}",
            },
        )

        return LVSearchPlan(
            mode="lv_number",
            search_scope="specified_cadastral_unit" if unit_hint else "unknown_cadastral_unit",
            primary_provider="eskn_portal",
            fallback_providers=("cica_portal",),
            instructions=tuple(instructions),
            links=links,
        )

    def _build_person_name_plan(self, *, person_name: str) -> LVSearchPlan:
        encoded_name = quote_plus(person_name)
        return LVSearchPlan(
            mode="person_name",
            search_scope="all_cadastral_units_slovakia",
            primary_provider="cica_portal",
            fallback_providers=("eskn_portal",),
            instructions=(
                "Run owner-name lookup in CICA across all cadastral units.",
                "From the owner results, open each matched list vlastníctva record.",
                "For each matched LV, download informatívny výpis in PDF/HTML format.",
                "If CICA result quality is limited, repeat in ESKN with municipality/cadastral filters.",
            ),
            links=(
                {
                    "label": "CICA owner lookup (primary)",
                    "url": f"{self._CICA_ROOT}/?search={encoded_name}",
                },
                {
                    "label": "ESKN portal (fallback)",
                    "url": f"{self._ESKN_ROOT}/uplny-zoznam?q={encoded_name}",
                },
            ),
        )
