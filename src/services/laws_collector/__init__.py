"""Laws collector service."""

from .country_registry import CountryLawsCollectorDefinition, get_country_laws_collector_definition
from .config import LawsCollectorConfig
from .domain import LawSnapshot, SyncSummary, UpdateCheckPlan
from .postgres_store import PostgresLawStore
from .service import LawsCollectorService
from .slovak_laws_collector import SlovakLawsCollectorService
from .sqlite_store import SqliteLawStore

__all__ = [
    "CountryLawsCollectorDefinition",
    "LawsCollectorConfig",
    "LawSnapshot",
    "LawsCollectorService",
    "SlovakLawsCollectorService",
    "SqliteLawStore",
    "PostgresLawStore",
    "SyncSummary",
    "UpdateCheckPlan",
    "get_country_laws_collector_definition",
]
