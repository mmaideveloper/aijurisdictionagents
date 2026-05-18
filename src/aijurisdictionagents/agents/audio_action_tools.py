from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .address_validator import AIAddressValidatorAgent
from .ai_web_search import CompanySearchAgent
from .car_validator import AICarValidatorAgent


@dataclass(frozen=True)
class ActionRecognition:
    tool_name: str
    message: str
    needs_parameters: tuple[str, ...] = ()
    result: dict[str, Any] | None = None


class AIActionToolRecognizerAgent:
    """Recognizes action intents and executes a mapped action agent."""

    def __init__(
        self,
        *,
        address_agent: AIAddressValidatorAgent | None = None,
        car_agent: AICarValidatorAgent | None = None,
        company_agent: CompanySearchAgent | None = None,
    ) -> None:
        self.address_agent = address_agent or AIAddressValidatorAgent()
        self.car_agent = car_agent or AICarValidatorAgent()
        self.company_agent = company_agent or CompanySearchAgent()

    def recognize(self, user_input: str) -> ActionRecognition | None:
        text = user_input.strip()
        lowered = text.lower()
        if not lowered:
            return None

        if any(k in lowered for k in ("company", "firma", "orsr", "orsk", "ico")):
            company_ref = self._extract_company_reference(text)
            if not company_ref:
                return ActionRecognition("ValidationCompany", "Using ValidationCompany (ORSK). Please provide company name or ICO.", ("company_name_or_ico",))
            prompt = self.company_agent.build_search_prompt(company_reference=company_ref, country="SK")
            return ActionRecognition("ValidationCompany", "Using ValidationCompany (ORSK). Running company validation.", result={"company_reference": company_ref, "search_prompt": prompt})

        if any(k in lowered for k in ("car", "vehicle", "spz", "vin", "vozid")):
            vin = self._extract_vin(text)
            spz = self._extract_spz(text)
            if not (vin or spz):
                return ActionRecognition("ValidationCar", "Using ValidationCar. Please provide SPZ or VIN.", ("spz_or_vin",))
            plan = self.car_agent.build_car_validation_plan(vin=vin, spz=spz)
            return ActionRecognition("ValidationCar", "Using ValidationCar. Running car validation.", result=plan)

        if any(k in lowered for k in ("address", "adresa", "registeradries")):
            payload = self.address_agent.validate_from_text(text)
            if not payload.get("ok"):
                return ActionRecognition("ValidationAddress", "Using ValidationAddress. Please provide full address.", ("address",), payload)
            return ActionRecognition("ValidationAddress", "Using ValidationAddress. Address mapped for validation.", result=payload)

        return None

    def _extract_company_reference(self, text: str) -> str:
        ico = re.search(r"\b\d{8}\b", text)
        if ico:
            return ico.group(0)
        cleaned = re.sub(r"\b(i want to|please|validate|company|firma|orsk|orsr|ico|chcem|overit|firmu)\b", "", text, flags=re.IGNORECASE)
        return cleaned.strip(" :-,")

    def _extract_vin(self, text: str) -> str:
        m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text.upper())
        return m.group(1) if m else ""

    def _extract_spz(self, text: str) -> str:
        m = re.search(r"\b([A-Z]{2}[0-9]{3}[A-Z]{2})\b", text.upper())
        return m.group(1) if m else ""


class AIAudioToolRecognizerAgent:
    """Recognizes STT intents and delegates action-intents to AIActionToolRecognizerAgent."""

    def __init__(self, action_agent: AIActionToolRecognizerAgent | None = None) -> None:
        self.action_agent = action_agent or AIActionToolRecognizerAgent()

    def recognize(self, transcript: str) -> ActionRecognition | None:
        text = transcript.strip().lower()
        if not text:
            return None
        if any(k in text for k in ("create case", "vytvor pripad", "novy pripad")):
            return ActionRecognition("CreateCase", "CreateCase recognized. Please provide case title.", ("title",))
        if any(k in text for k in ("prepare document", "priprav dokument", "zmluvu", "splnomocnen")):
            return ActionRecognition("PrepareDocuments", "PrepareDocuments recognized. I will prepare final document and convert to PDF.")
        if any(k in text for k in ("send document", "posli dokument", "email")):
            return ActionRecognition("SendDocumentsByEmail", "SendDocumentsByEmail recognized. I will prepare missing document and send it to your login email.")
        return self.action_agent.recognize(transcript)
