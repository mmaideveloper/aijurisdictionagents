from __future__ import annotations

import os

# Most tests intentionally stay offline/deterministic and still use the pre-existing
# mock/cloud embedding path unless they explicitly opt into the local model path.
os.environ.setdefault("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")
