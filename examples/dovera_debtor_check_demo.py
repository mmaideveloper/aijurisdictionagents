"""Minimal runnable demo for the Dôvera debtor-check tool.

Run:
    python examples/dovera_debtor_check_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.tools.dovera_debtors import DoveraDebtorCheckTool  # noqa: E402


_FIXTURE_HTML = """
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
            </div>
            <div class="item-sum">9&nbsp;545,70&nbsp;&euro; </div>
          </div>
        </div>
      </li>
    </ul>
    <span>Údaje v uvedenom zozname preto majú len informatívny charakter, nie sú použiteľné pre právne úkony a nenahrádzajú potvrdenia o stave pohľadávok.</span>
  </body>
</html>
"""


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    tool = DoveraDebtorCheckTool(requester=lambda _url: (200, "text/html", _FIXTURE_HTML))
    result = tool.run(search_query="HF STEEL")
    print(result.tool_name)
    print(result.message)
    for record in result.records:
        print(record)
