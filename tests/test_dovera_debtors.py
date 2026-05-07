from __future__ import annotations

from aijurisdictionagents.tools.dovera_debtors import DoveraDebtorCheckTool
from aijurisdictionagents.tools.registry import build_default_tool_registry


def test_dovera_debtor_tool_parses_result_record_and_evidence_fields() -> None:
    html = """
    <html>
      <body>
        <h3 class="mb--large">Zoznam dlžníkov k dátumu 25. apríl 2026</h3>
        <ul class="no-pad list--unstyled">
          <li class="dlznici__item">
            <div class="grid grid--no-gutters">
              <div class="grid__col grid__col--shrink d-flex align-items-top align-items-middle--xl">
                <img class="item-icon" alt="" title="Hromadný platiteľ poistného" src="icon.svg" width="24" height="24"/>
              </div>
              <div class="grid__col grid__col--auto dlznici__item__content">
                <div>
                  <p class="item-name" id="item-id-4251258">HF STEEL, S.R.O.</p>
                  <p class="item-adress">OKRUŽNÁ 3239, 90001 MODRA<br />IČO: 36547204 </p>
                  <div class="d-flex item-additional no-mrg-top--xl align-items-middle--m">
                    <img src="show.svg" alt="icon-show">
                    <span class="text-small--14px">Detail nájdete vo svojej <a href="https://ep.dovera.sk/Login.aspx?ReturnUrl=%2f" class="link text-bold">e-pobočke</a></span>
                  </div>
                </div>
                <div class="item-sum">9&nbsp;545,70&nbsp;&euro; </div>
                <div class="item-buttons">
                  <button type="button" onclick="window.location.href='/overenia/dlznici/zoznam-dlznikov?action=payment&amp;id=4251258&amp;q=hf+steel&amp;typ=HPP'">Zaplatiť</button>
                  <button type="button" onclick="window.location.href='/overenia/dlznici/zoznam-dlznikov?action=claim&amp;id=4251258&amp;q=hf+steel&amp;typ=HPP'">Namietať</button>
                </div>
              </div>
            </div>
          </li>
        </ul>
        <span>Údaje v uvedenom zozname preto majú len informatívny charakter, nie sú použiteľné pre právne úkony a nenahrádzajú potvrdenia o stave pohľadávok.</span>
      </body>
    </html>
    """
    tool = DoveraDebtorCheckTool(requester=lambda _url: (200, "text/html", html))

    result = tool.run(search_query="HF STEEL")

    assert result.ok is True
    assert len(result.records) == 1
    record = result.records[0]
    assert record["debtor_name"] == "HF STEEL, S.R.O."
    assert record["registration_number"] == "36547204"
    assert record["address"] == "OKRUŽNÁ 3239, 90001 MODRA"
    assert record["debt_amount_eur"] == 9545.70
    assert record["source_snapshot_date_iso"] == "2026-04-25"
    assert record["match_type"] == "partial_name"
    assert record["match_confidence"] >= 0.8
    assert "informatívny charakter" in str(record["advisory_notice"])
    assert str(record["payment_url"]).startswith("https://www.dovera.sk/overenia/dlznici/zoznam-dlznikov?action=payment")
    assert str(record["claim_url"]).startswith("https://www.dovera.sk/overenia/dlznici/zoznam-dlznikov?action=claim")


def test_dovera_debtor_tool_returns_empty_records_for_no_match() -> None:
    html = """
    <html>
      <body>
        <p class="form-message">Pre „Matonok” sme nenašli žiadne výsledky v zozname dlžníkov.</p>
      </body>
    </html>
    """
    tool = DoveraDebtorCheckTool(requester=lambda _url: (200, "text/html", html))

    result = tool.run(search_query="Matonok")

    assert result.ok is True
    assert result.records == ()
    assert result.message == "No Dôvera debtor records found."


def test_registry_exposes_dovera_debtor_check_tool() -> None:
    registry = build_default_tool_registry()

    assert registry.has_tool("dovera_debtor_check")
