from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import LawsCollectorConfig
from .domain import LawSnapshot
from .service import LawsCollectorService
from .slovak_laws_collector import SlovakLawsCollectorService
from .slovak_source_fixtures import baseline_snapshots as slovak_baseline_snapshots
from .slovak_source_fixtures import delta_snapshots as slovak_delta_snapshots

SnapshotFactory = Callable[[], tuple[LawSnapshot, ...]]
ServiceFactory = Callable[[LawsCollectorConfig, object], LawsCollectorService]


@dataclass(frozen=True)
class CountryLawsCollectorDefinition:
    collector_name: str
    country_code: str
    cloud_database_name: str
    service_factory: ServiceFactory
    baseline_snapshots_factory: SnapshotFactory
    delta_snapshots_factory: SnapshotFactory

    def create_service(self, *, config: LawsCollectorConfig, store: object) -> LawsCollectorService:
        return self.service_factory(config, store)

    def baseline_snapshots(self) -> tuple[LawSnapshot, ...]:
        return self.baseline_snapshots_factory()

    def delta_snapshots(self) -> tuple[LawSnapshot, ...]:
        return self.delta_snapshots_factory()


_COUNTRY_COLLECTORS: dict[str, CountryLawsCollectorDefinition] = {
    "SK": CountryLawsCollectorDefinition(
        collector_name="slovak_laws_collector",
        country_code="SK",
        cloud_database_name="laws_sk",
        service_factory=lambda config, store: SlovakLawsCollectorService(config=config, store=store),
        baseline_snapshots_factory=slovak_baseline_snapshots,
        delta_snapshots_factory=slovak_delta_snapshots,
    )
}


def get_country_laws_collector_definition(country_code: str) -> CountryLawsCollectorDefinition:
    normalized_country_code = country_code.strip().upper()
    definition = _COUNTRY_COLLECTORS.get(normalized_country_code)
    if definition is None:
        supported = ", ".join(sorted(_COUNTRY_COLLECTORS))
        raise ValueError(
            f"Unsupported LAWS_COUNTRY '{country_code}'. Supported countries: {supported}"
        )
    return definition
