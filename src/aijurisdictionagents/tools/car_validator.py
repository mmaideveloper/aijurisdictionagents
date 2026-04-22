from __future__ import annotations

import os
from typing import Any

from ..car_validation import AICarValidatorAgent, VehicleCheckApiClient
from .base import ToolDefinition, ToolResult


class SlovakiaCarValidatorTool:
    """Validate Slovak car identifiers and build VIN/SPZ verification workflow."""

    def __init__(self, *, agent: AICarValidatorAgent | None = None) -> None:
        self._agent = agent or AICarValidatorAgent()
        self._api_base_url = os.getenv("CAR_VALIDATION_API_BASE_URL", "").strip()
        self._api_key = os.getenv("CAR_VALIDATION_API_KEY", "").strip()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="slovakia_car_validate",
            purpose=(
                "Validate VIN format/checksum, evaluate Slovak SPZ plausibility, and prepare a Slovakia car "
                "verification plan including ownership-history access constraints. "
                "When configured, execute API checks for wanted records, vehicle blocking, leasing, liens, "
                "owner count, and damage history."
            ),
            input_fields=("vin", "spz", "run_api_check"),
            requires_explicit_user_confirmation=True,
        )

    def run(self, **kwargs: Any) -> ToolResult:
        vin = str(kwargs.get("vin") or "").strip()
        spz = str(kwargs.get("spz") or "").strip()
        run_api_check = bool(kwargs.get("run_api_check", True))
        result = self._agent.build_car_validation_plan(vin=vin, spz=spz)
        if not result.get("ok"):
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=str(result.get("message") or "Car validation failed."),
            )

        record = {
            "vin": result["query"]["vin"],
            "spz": result["query"]["spz"],
            "spz_probable_slovak": self._agent.is_probable_slovak_spz(spz),
            "plan": result["plan"],
            "api_check": {
                "ok": False,
                "message": "API check skipped (CAR_VALIDATION_API_BASE_URL not configured).",
                "result": {},
            },
        }
        if run_api_check and self._api_base_url:
            api_client = VehicleCheckApiClient(base_url=self._api_base_url, api_key=self._api_key)
            api_result = self._agent.check_vehicle_via_api(vin=vin, spz=spz, client=api_client)
            record["api_check"] = api_result
        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=(record,),
            message=str(result.get("message") or "Car validation plan prepared."),
        )
