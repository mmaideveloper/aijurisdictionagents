from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class AddressMapping:
    original_text: str
    street: str
    house_number: str
    postal_code: str
    city: str
    okres: str
    kraj: str

    def as_dict(self) -> dict[str, str]:
        return {
            "original_text": self.original_text,
            "street": self.street,
            "house_number": self.house_number,
            "postal_code": self.postal_code,
            "city": self.city,
            "okres": self.okres,
            "kraj": self.kraj,
        }


class AIAddressValidatorAgent:
    """Extract Slovak address candidates and prepare registeradries lookup mapping."""

    name: str = "AIAddressValidatorAgent"
    base_lookup_url: str = "https://registeradries.sk/"

    _POSTAL_CITY_RE = re.compile(
        r"\b(?P<postal>\d{3}\s?\d{2})\s+(?P<city>[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž\- ]{2,})\b"
    )
    _STREET_NUMBER_RE = re.compile(
        r"(?P<street>[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž0-9\.\- ]+?)\s+(?P<number>\d+[A-Za-z]?/?\d*)"
    )

    _CITY_TO_KRAJ_OKRES: dict[str, tuple[str, str]] = {
        "bratislava": ("Bratislavský kraj", "Bratislava"),
        "kosice": ("Košický kraj", "Košice"),
        "žilina": ("Žilinský kraj", "Žilina"),
        "zilina": ("Žilinský kraj", "Žilina"),
        "trnava": ("Trnavský kraj", "Trnava"),
        "nitra": ("Nitriansky kraj", "Nitra"),
        "trenčín": ("Trenčiansky kraj", "Trenčín"),
        "trencin": ("Trenčiansky kraj", "Trenčín"),
        "banská bystrica": ("Banskobystrický kraj", "Banská Bystrica"),
        "banska bystrica": ("Banskobystrický kraj", "Banská Bystrica"),
        "prešov": ("Prešovský kraj", "Prešov"),
        "presov": ("Prešovský kraj", "Prešov"),
    }

    def extract_mapping(self, text: str) -> AddressMapping | None:
        candidate = " ".join(text.strip().split())
        if not candidate:
            return None

        postal_match = self._POSTAL_CITY_RE.search(candidate)
        postal_code = ""
        city = ""
        if postal_match is not None:
            postal_code = postal_match.group("postal").replace(" ", "")
            city = postal_match.group("city").strip(" ,.;")

        street_match = self._STREET_NUMBER_RE.search(candidate)
        street = ""
        house_number = ""
        if street_match is not None:
            street = street_match.group("street").strip(" ,.;")
            house_number = street_match.group("number").strip(" ,.;")
            street = re.sub(
                r"^(?:doručovaciu|dorucovaciu|moju|moja|adresu|adresa|nastavte|na)\s+",
                "",
                street,
                flags=re.IGNORECASE,
            ).strip(" ,.;")

        if not city:
            parts = [part.strip() for part in re.split(r",|;", candidate) if part.strip()]
            if parts:
                city = parts[-1]

        kraj, okres = self._resolve_region(city)
        if not any((street, house_number, postal_code, city)):
            return None

        return AddressMapping(
            original_text=text.strip(),
            street=street,
            house_number=house_number,
            postal_code=postal_code,
            city=city,
            okres=okres,
            kraj=kraj,
        )

    def build_registeradries_lookup_url(self, mapping: AddressMapping) -> str:
        params = {
            "q": mapping.original_text,
            "kraj": mapping.kraj,
            "okres": mapping.okres,
            "city": mapping.city,
            "street": mapping.street,
            "house_number": mapping.house_number,
            "psc": mapping.postal_code,
        }
        cleaned = {key: value for key, value in params.items() if value}
        if not cleaned:
            return self.base_lookup_url
        return f"{self.base_lookup_url}?{urlencode(cleaned)}"

    def validate_from_text(self, text: str) -> dict[str, Any]:
        mapping = self.extract_mapping(text)
        if mapping is None:
            return {
                "ok": False,
                "message": "No Slovak address candidate detected in text.",
                "mapping": {},
                "lookup_url": self.base_lookup_url,
            }
        return {
            "ok": True,
            "message": "Address candidate mapped for registeradries lookup.",
            "mapping": mapping.as_dict(),
            "lookup_url": self.build_registeradries_lookup_url(mapping),
        }

    def _resolve_region(self, city: str) -> tuple[str, str]:
        normalized_city = " ".join(city.lower().split())
        return self._CITY_TO_KRAJ_OKRES.get(normalized_city, ("", ""))
