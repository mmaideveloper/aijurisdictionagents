from __future__ import annotations

import os

# API default runtime provider is Azure Foundry.
# Tests use mock provider to stay deterministic and independent from cloud credentials.
os.environ.setdefault("LLM_PROVIDER", "mock")
