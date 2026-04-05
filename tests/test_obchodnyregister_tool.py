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

    assert "https://sluzby.orsr.sk/Vyhladavanie?" in url
    assert "CurrentPage=1" in url
    assert "Take=10" in url
    assert "Filter.CorporateBodyFullNameOrRegistrationNumber=Esolution" in url
    assert "Filter.PhysicalPersonName=Matonok" in url
    assert "Filter.IncludeTerminated=true" in url


def test_obchodnyregister_run_parses_json_payload() -> None:
    payload = (
        '{"items":[{"CorporateBodyFullName":"ESOLUTION s.r.o.",' 
        '"RegistrationNumber":"12345678","RegisteredSeat":"Bratislava",'
        '"Status":"Active"}]}'
    )
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", payload))

    result = tool.run(company_name_or_registration="Esolution", person_name="Matonok")

    assert result.ok
    assert len(result.records) == 1
    assert result.records[0]["name"] == "ESOLUTION s.r.o."
    assert result.records[0]["registration_number"] == "12345678"


def test_obchodnyregister_run_handles_html_payload() -> None:
    html = """
    <table>
      <tr><th>Name</th><th>ICO</th><th>Seat</th><th>Status</th></tr>
      <tr><td>ESOLUTION s.r.o.</td><td>IČO: 12345678</td><td>Bratislava</td><td>Active</td></tr>
    </table>
    """
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "text/html", html))

    result = tool.run(company_name_or_registration="Esolution")

    assert result.ok
    assert len(result.records) == 1
    assert result.records[0]["registration_number"] == "12345678"


def test_obchodnyregister_run_requires_company_query() -> None:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", "[]"))

    result = tool.run(company_name_or_registration="")

    assert not result.ok
    assert "required" in result.message
