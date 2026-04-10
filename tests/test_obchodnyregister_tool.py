from __future__ import annotations

from aijurisdictionagents.tools.obchodnyregister import ObchodnyRegisterTool


def test_obchodnyregister_build_search_url_uses_expected_parameters() -> None:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", "[]"))
    url = tool.build_search_url(
        company_name_or_registration="Esolution",
        person_name="Matonok",
        include_terminated=True,
        current_page=1,
        take=10,
    )

    assert "https://sluzby.orsr.sk/api/legal-person?" in url
    assert "Skip=0" in url
    assert "Take=10" in url
    assert "Filter.CorporateBodyFullNameOrRegistrationNumber=Esolution" in url
    assert "Filter.PhysicalPersonName=Matonok" in url
    assert "Filter.IncludeTerminated=true" in url


def test_obchodnyregister_run_parses_filtered_count_data_payload_and_prefers_exact_match() -> None:
    search_payload = (
        '{"filteredCount":2,"data":['
        '{"corporateBodyFullName":"Automotive solutions SK s. r. o.",'
        '"registrationNumber":"51962977",'
        '"fileReference":{"section":"Sro","insertNumber":37130,"court":"R"},'
        '"physicalAddressLine1":"Konventná 7",'
        '"physicalAddressLine2":"811 03 Bratislava - mestská časť Staré Mesto"},'
        '{"corporateBodyFullName":"ESolutions SK s.r.o.",'
        '"registrationNumber":"46491261",'
        '"fileReference":{"section":"Sro","insertNumber":25400,"court":"P"},'
        '"physicalAddressLine1":"Partizánska 665",'
        '"physicalAddressLine2":"059 18 Spišské Bystré"}'
        ']}'
    )
    detail_payload = (
        '{"legalPerson":{"corporateBody":{'
        '"corporateBodyFullName":[{"current":true,"value":"ESolutions SK s.r.o."}],'
        '"authorizationToExecute":[{"current":true,"value":"V mene spoločnosti koná konateľ samostatne."}],'
        '"equity":[{"current":true,"equityValue":5000.0,"currency":{"item":"EUR"}}],'
        '"deposits":[{"current":true,"stakeholder":[{"current":true,"value":"RNDr. Marek Matonok"}],"depositValue":5000.0,"depositPayedValue":5000.0,"currency":{"item":{"codelistItem":{"itemName":"EUR"}}}}],'
        '"stakeholder":[{"current":true,"stakeholderType":{"item":{"codelistItem":{"itemName":"spoločník"}}},"personData":{"physicalPerson":{"personName":{"formattedName":"RNDr. Marek Matonok"}},"physicalAddress":[{"streetName":"Partizánska","buildingNumber":"665/101","municipality":{"item":"Spišské Bystré"},"country":{"item":"Slovenská republika"},"deliveryAddress":{"postalCode":"05918"}}]}}],'
        '"statutoryBody":[{"current":true,"functionCreationDate":"2012-01-17T00:00:00","personData":{"physicalPerson":{"personName":{"formattedName":"RNDr. Marek Matonok"}},"physicalAddress":[{"streetName":"Partizánska","buildingNumber":"665","municipality":{"item":"Spišské Bystré"},"country":{"item":"Slovenská republika"},"deliveryAddress":{"postalCode":"05918"}}]}}]'
        '},'
        '"physicalAddress":[{"current":true,"streetName":"Partizánska","buildingNumber":"665","municipality":{"item":"Spišské Bystré"},"deliveryAddress":{"postalCode":"05918"}}],'
        '"id":[{"current":true,"identifierValue":"46491261"}]}}'
    )

    def _requester(url: str) -> tuple[int, str, str]:
        if "extract-full" in url:
            return 200, "application/json", detail_payload
        return 200, "application/json", search_payload

    tool = ObchodnyRegisterTool(requester=_requester)

    result = tool.run(company_name_or_registration="ESolutions SK s.r.o.", person_name="Matonok")

    assert result.ok
    assert len(result.records) == 2
    assert result.records[0]["name"] == "ESolutions SK s.r.o."
    assert result.records[0]["registration_number"] == "46491261"
    assert result.records[0]["seat"] == "Partizánska 665, 059 18 Spišské Bystré"
    assert result.records[0]["status"] == "Aktívna"
    assert result.records[0]["authorization_to_execute"] == "V mene spoločnosti koná konateľ samostatne."
    assert result.records[0]["equity_value"] == "5000 EUR"
    assert result.records[0]["stakeholders"][0]["name"] == "RNDr. Marek Matonok"
    assert result.records[0]["deposits"][0]["deposit_value"] == "5000 EUR"
    assert result.records[0]["statutory_representatives"][0]["name"] == "RNDr. Marek Matonok"
    assert result.records[1]["name"] == "Automotive solutions SK s. r. o."


def test_obchodnyregister_run_marks_company_in_liquidation_from_detail() -> None:
    search_payload = (
        '{"filteredCount":1,"data":['
        '{"corporateBodyFullName":"Example s.r.o. v likvidácii",'
        '"registrationNumber":"12345678",'
        '"fileReference":{"section":"Sro","insertNumber":1,"court":"B"},'
        '"physicalAddressLine1":"Main 1",'
        '"physicalAddressLine2":"811 01 Bratislava"}'
        ']}'
    )
    detail_payload = (
        '{"legalPerson":{"corporateBody":{"corporateBodyFullName":[{"current":true,"value":"Example s.r.o. v likvidácii"}]}}}'
    )

    def _requester(url: str) -> tuple[int, str, str]:
        if "extract-full" in url:
            return 200, "application/json", detail_payload
        return 200, "application/json", search_payload

    tool = ObchodnyRegisterTool(requester=_requester)

    result = tool.run(company_name_or_registration="Example s.r.o.")

    assert result.ok
    assert result.records[0]["status"] == "v likvidácii"


def test_obchodnyregister_run_rejects_non_json_payload() -> None:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "text/html", "<html>maintenance</html>"))

    result = tool.run(company_name_or_registration="Esolution")

    assert not result.ok
    assert "expected JSON payload" in result.message


def test_obchodnyregister_run_requires_company_query() -> None:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", "[]"))

    result = tool.run(company_name_or_registration="")

    assert not result.ok
    assert "required" in result.message
