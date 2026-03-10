"""Slovak laws collector service."""

from .config import LawsCollectorConfig
from .domain import SyncSummary
from .service import SlovakLawsCollectorService
from .sqlite_store import SqliteLawStore

__all__ = [
    "LawsCollectorConfig",
    "SlovakLawsCollectorService",
    "SqliteLawStore",
    "SyncSummary",
]
