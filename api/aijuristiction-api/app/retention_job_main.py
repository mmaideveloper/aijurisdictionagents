from __future__ import annotations

import json

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.compliance import ComplianceService


def main() -> int:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    result = ComplianceService(store).run_retention()
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
