from __future__ import annotations

from aijurisdictionagents.car_validation import AICarValidatorAgent, VehicleCheckApiClient
from aijurisdictionagents.tools import answer_slovak_car_validation_question
from aijurisdictionagents.tools.car_validator import SlovakiaCarValidatorTool
from aijurisdictionagents.tools.registry import build_default_tool_registry


def test_car_validator_accepts_valid_vin_and_builds_plan() -> None:
    result = AICarValidatorAgent().build_car_validation_plan(
        vin="1HGCM82633A004352",
        spz="BA123AB",
    )

    assert result["ok"] is True
    plan = result["plan"]
    assert plan["vin_valid"] is True
    assert plan["mode"] == "vin_spz"
    assert plan["ownership_history_available"] is False


def test_car_validator_rejects_missing_identifiers() -> None:
    result = AICarValidatorAgent().build_car_validation_plan()
    assert result["ok"] is False


def test_registry_exposes_slovakia_car_validate_tool() -> None:
    registry = build_default_tool_registry()

    assert registry.has_tool("slovakia_car_validate")
    result = registry.run("slovakia_car_validate", vin="1HGCM82633A004352", spz="BA123AB")

    assert result.ok is True
    assert result.records


def test_answer_slovak_car_validation_question_uses_tool() -> None:
    response = answer_slovak_car_validation_question(
        "Over mi auto VIN 1HGCM82633A004352 a SPZ BA123AB.",
    )

    assert response is not None
    assert "VIN" in response
    assert "História vlastníkov" in response


def test_car_validator_api_check_parses_required_vehicle_fields() -> None:
    client = VehicleCheckApiClient(
        base_url="https://vehicle-checks.example.com/api",
        requester=lambda _url, headers: (
            200,
            "application/json",
            (
                '{"national_wanted_records":"not_found","vehicle_blocking":"none",'
                '"leasing_status":"inactive","lien_status":"none","owner_count":3,'
                '"damage_records":[{"date":"2024-01-01","source":"insurer","description":"rear bumper"}],'
                '"source":"fixture"}'
            ),
        ),
    )
    result = AICarValidatorAgent().check_vehicle_via_api(
        vin="1HGCM82633A004352",
        spz="BA123AB",
        client=client,
    )
    assert result["ok"] is True
    payload = result["result"]
    assert payload["national_wanted_records"] == "not_found"
    assert payload["vehicle_blocking"] == "none"
    assert payload["leasing_status"] == "inactive"
    assert payload["lien_status"] == "none"
    assert payload["owner_count"] == 3
    assert payload["damage_records"]
    assert payload["vehicle_info"]["brand"] == ""


def test_tool_runs_api_check_when_base_url_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("CAR_VALIDATION_API_BASE_URL", "https://vehicle-checks.example.com/api")
    monkeypatch.setenv("CAR_VALIDATION_API_KEY", "secret")

    class _FakeClient:
        def __init__(self, *, base_url: str, api_key: str) -> None:
            assert base_url == "https://vehicle-checks.example.com/api"
            assert api_key == "secret"

        def check_vehicle(self, *, vin: str, spz: str = ""):
            return type(
                "Result",
                (),
                {
                    "as_dict": lambda self: {
                        "vin": vin,
                        "spz": spz,
                        "national_wanted_records": "not_found",
                        "vehicle_blocking": "none",
                        "leasing_status": "inactive",
                        "lien_status": "none",
                        "owner_count": 2,
                        "damage_records": [],
                        "vehicle_info": {"brand": "Skoda", "model": "Octavia", "year": "2020", "color": ""},
                        "source": "fixture",
                        "raw": {},
                    }
                },
            )()

    monkeypatch.setattr("aijurisdictionagents.tools.car_validator.VehicleCheckApiClient", _FakeClient)
    tool = SlovakiaCarValidatorTool()
    result = tool.run(vin="1HGCM82633A004352", spz="BA123AB", run_api_check=True)

    assert result.ok is True
    assert result.records[0]["api_check"]["ok"] is True
    assert result.records[0]["api_check"]["result"]["owner_count"] == 2


def test_car_validator_api_check_supports_alias_fields_from_external_specs() -> None:
    client = VehicleCheckApiClient(
        base_url="https://vehicle-checks.example.com/api",
        requester=lambda _url, headers: (
            200,
            "application/json",
            (
                '{"nationalWantedRecords":"clear","vehicleBlocking":"no","leasingStatus":"no",'
                '"lienStatus":"no","numberOfOwners":"5","damageRecords":[{"date":"2023-01-01","source":"db","description":"front"}],'
                '"make":"Skoda","vehicleModel":"Octavia","modelYear":"2020","provider":"vehicleinfo"}'
            ),
        ),
    )
    result = AICarValidatorAgent().check_vehicle_via_api(
        vin="1HGCM82633A004352",
        spz="BA123AB",
        client=client,
    )
    payload = result["result"]
    assert payload["national_wanted_records"] == "clear"
    assert payload["vehicle_blocking"] == "no"
    assert payload["leasing_status"] == "no"
    assert payload["lien_status"] == "no"
    assert payload["owner_count"] == 5
    assert payload["vehicle_info"]["brand"] == "Skoda"
    assert payload["vehicle_info"]["model"] == "Octavia"
    assert payload["vehicle_info"]["year"] == "2020"


def test_vehicle_api_client_builds_databazavozidiel_query_urls() -> None:
    client = VehicleCheckApiClient(base_url="https://www.databazavozidiel.sk")
    assert (
        client.build_lookup_url(vin="", spz="BA123AB")
        == "https://www.databazavozidiel.sk/api/vehicles?ecv=BA123AB"
    )
    assert (
        client.build_lookup_url(vin="1HGCM82633A004352", spz="")
        == "https://www.databazavozidiel.sk/api/vehicles?vin=1HGCM82633A004352"
    )
    assert (
        client.build_lookup_url(vin="1HGCM82633A004352", spz="BA123AB")
        == "https://www.databazavozidiel.sk/api/vehicles?ecv=BA123AB&vin=1HGCM82633A004352"
    )
