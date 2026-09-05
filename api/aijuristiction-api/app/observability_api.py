from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.observability import (
    ApplicationName,
    AzureApplicationInsightsLogService,
    LogLevel,
    LogSource,
    ObservabilityConfigurationError,
    serialize_query_result,
)
from app.security import require_api_key

router = APIRouter(
    prefix="/v1/observability",
    tags=["observability"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/logs")
def get_application_insights_logs(
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    application: ApplicationName | None = None,
    level: LogLevel | None = None,
    source: LogSource | None = None,
    correlation_id: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, object]:
    try:
        service = AzureApplicationInsightsLogService.from_env()
    except ObservabilityConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        query_args: dict[str, Any] = {
            "minutes": minutes,
            "limit": limit,
            "application": application,
            "level": level,
            "source": source,
        }
        if correlation_id:
            query_args["correlation_id"] = correlation_id
        result = service.query_logs(
            **query_args,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Azure Application Insights query failed: {exc}",
        ) from exc
    return serialize_query_result(result)
