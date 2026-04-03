from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
import json
import os
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.monitor.query import LogsQueryClient

ApplicationName = Literal["api", "document_processor", "laws_collector"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]
LogSource = Literal["trace", "exception", "request"]

_APPLICATION_FILTERS: dict[ApplicationName, tuple[str, ...]] = {
    "api": ("api",),
    "document_processor": ("document_processor",),
    "laws_collector": ("laws_collector",),
}


class ObservabilityConfigurationError(RuntimeError):
    """Raised when the Azure observability endpoint is not configured."""


@dataclass(frozen=True)
class ObservabilityLogRecord:
    timestamp: str
    application: ApplicationName
    level: LogLevel
    source: LogSource
    message: str
    operation_id: str
    request_id: str
    operation_name: str
    result_code: str
    success: bool | None
    duration_ms: float | None
    exception_type: str
    problem_id: str


@dataclass(frozen=True)
class ObservabilityQueryResult:
    minutes: int
    application: ApplicationName | None
    level: LogLevel | None
    source: LogSource | None
    total_count: int
    by_application: dict[str, int]
    by_level: dict[str, int]
    by_source: dict[str, int]
    records: list[ObservabilityLogRecord]


class AzureApplicationInsightsLogService:
    def __init__(
        self,
        *,
        workspace_name: str,
        workspace_id: str,
        connection_string: str,
        managed_identity_name: str,
        subscription_id: str,
        resource_group: str,
    ) -> None:
        self._workspace_name = workspace_name
        self._workspace_id = workspace_id
        self._connection_string = connection_string
        self._managed_identity_name = managed_identity_name
        self._subscription_id = subscription_id
        self._resource_group = resource_group

    @classmethod
    def from_env(cls) -> "AzureApplicationInsightsLogService":
        connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
        workspace_name = os.getenv("AZURE_LOG_ANALYTICS_WORKSPACE_NAME", "").strip()
        workspace_id = os.getenv("APPLICATIONINSIGHTS_LOGS_WORKSPACE_ID", "").strip()
        managed_identity_name = os.getenv("AZURE_MANAGED_IDENTITY_NAME", "").strip()
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
        resource_group = os.getenv("AZURE_RESOURCE_GROUP", "").strip()

        if not connection_string:
            raise ObservabilityConfigurationError(
                "APPLICATIONINSIGHTS_CONNECTION_STRING is not configured."
            )
        if not workspace_name and not workspace_id:
            raise ObservabilityConfigurationError(
                "AZURE_LOG_ANALYTICS_WORKSPACE_NAME is not configured."
            )
        if not workspace_id and (not subscription_id or not resource_group):
            raise ObservabilityConfigurationError(
                "AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP are required to resolve "
                "AZURE_LOG_ANALYTICS_WORKSPACE_NAME."
            )

        return cls(
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            connection_string=connection_string,
            managed_identity_name=managed_identity_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
        )

    def query_logs(
        self,
        *,
        minutes: int,
        limit: int,
        application: ApplicationName | None = None,
        level: LogLevel | None = None,
        source: LogSource | None = None,
    ) -> ObservabilityQueryResult:
        base_query = _build_base_query(
            application=application,
            level=level,
            source=source,
        )
        workspace_id = self._resolve_workspace_id()
        client = self._build_client()
        summary_result = client.query_workspace(
            workspace_id=workspace_id,
            query=_build_summary_query(base_query),
            timespan=timedelta(minutes=minutes),
        )
        records_result = client.query_workspace(
            workspace_id=workspace_id,
            query=_build_records_query(base_query, limit=limit),
            timespan=timedelta(minutes=minutes),
        )

        summary_rows = list(_result_rows(summary_result))
        records = [_row_to_record(row) for row in _result_rows(records_result)]
        by_application = _counter_from_rows(summary_rows, "application")
        by_level = _counter_from_rows(summary_rows, "level")
        by_source = _counter_from_rows(summary_rows, "source")

        return ObservabilityQueryResult(
            minutes=minutes,
            application=application,
            level=level,
            source=source,
            total_count=sum(_to_int(row.get("count", 0)) for row in summary_rows),
            by_application=by_application,
            by_level=by_level,
            by_source=by_source,
            records=records,
        )

    def _build_client(self) -> LogsQueryClient:
        return LogsQueryClient(self._build_credential())

    def _build_credential(self) -> TokenCredential:
        managed_identity_client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
        has_explicit_env_credential = bool(
            os.getenv("AZURE_CLIENT_SECRET", "").strip()
            or os.getenv("AZURE_CLIENT_CERTIFICATE_PATH", "").strip()
            or os.getenv("AZURE_FEDERATED_TOKEN_FILE", "").strip()
        )
        if has_explicit_env_credential:
            return DefaultAzureCredential(exclude_interactive_browser_credential=True)
        if self._managed_identity_name and managed_identity_client_id:
            return ManagedIdentityCredential(client_id=managed_identity_client_id)
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)

    def _resolve_workspace_id(self) -> str:
        if self._workspace_id:
            return self._workspace_id

        if not self._workspace_name:
            raise ObservabilityConfigurationError(
                "AZURE_LOG_ANALYTICS_WORKSPACE_NAME is not configured."
            )
        if not self._subscription_id or not self._resource_group:
            raise ObservabilityConfigurationError(
                "AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP are required to resolve "
                "AZURE_LOG_ANALYTICS_WORKSPACE_NAME."
            )

        workspace = self._arm_get(
            resource_path=(
                f"/subscriptions/{self._subscription_id}/resourceGroups/{self._resource_group}"
                f"/providers/Microsoft.OperationalInsights/workspaces/{self._workspace_name}"
            ),
            api_version="2023-09-01",
        )
        properties = workspace.get("properties")
        if not isinstance(properties, dict):
            raise ObservabilityConfigurationError(
                "Log Analytics workspace response did not include properties."
            )

        customer_id = str(properties.get("customerId", "")).strip()
        if not customer_id:
            raise ObservabilityConfigurationError(
                "Resolved Log Analytics workspace did not include a customerId."
            )

        self._workspace_id = customer_id
        return self._workspace_id

    def _arm_get(self, *, resource_path: str, api_version: str) -> dict[str, object]:
        credential = self._build_credential()
        token = credential.get_token("https://management.azure.com/.default")
        request = Request(
            url=f"https://management.azure.com{resource_path}?api-version={api_version}",
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = _read_http_error_detail(exc)
            raise ObservabilityConfigurationError(
                "Failed to resolve Azure resource metadata for observability: "
                f"HTTP {exc.code} {detail}"
            ) from exc
        except URLError as exc:
            raise ObservabilityConfigurationError(
                f"Failed to reach Azure management endpoint for observability: {exc.reason}"
            ) from exc

        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ObservabilityConfigurationError(
                "Azure management response for observability was not a JSON object."
            )
        return {str(key): value for key, value in data.items()}


def serialize_query_result(result: ObservabilityQueryResult) -> dict[str, object]:
    return {
        "filters": {
            "minutes": result.minutes,
            "application": result.application,
            "level": result.level,
            "source": result.source,
        },
        "summary": {
            "total_count": result.total_count,
            "by_application": result.by_application,
            "by_level": result.by_level,
            "by_source": result.by_source,
        },
        "records": [asdict(record) for record in result.records],
    }


def _build_base_query(
    *,
    application: ApplicationName | None,
    level: LogLevel | None,
    source: LogSource | None,
) -> str:
    filters: list[str] = []
    if application is not None:
        values = ", ".join(f"'{name}'" for name in _APPLICATION_FILTERS[application])
        filters.append(f"application in ({values})")
    if level is not None:
        filters.append(f"level == '{level}'")
    if source is not None:
        filters.append(f"source == '{source}'")

    filter_block = ""
    if filters:
        filter_block = "\n| where " + "\n| where ".join(filters)

    return (
        _UNION_QUERY
        + filter_block
    )


def _build_summary_query(base_query: str) -> str:
    return (
        base_query
        + "\n| summarize count=count() by application, level, source"
        + "\n| order by application asc, level asc, source asc"
    )


def _build_records_query(base_query: str, *, limit: int) -> str:
    return (
        base_query
        + "\n| order by timestamp desc"
        + f"\n| take {limit}"
    )


def _result_rows(result: object) -> Iterable[dict[str, object]]:
    tables = getattr(result, "tables", None)
    if not isinstance(tables, Sequence):
        return ()

    rows: list[dict[str, object]] = []
    for table in tables:
        columns_raw = getattr(table, "columns", ())
        columns = [str(getattr(column, "name", column)) for column in columns_raw]
        for row in getattr(table, "rows", ()):
            if isinstance(row, dict):
                rows.append({str(key): value for key, value in row.items()})
                continue
            if not isinstance(row, Sequence):
                continue
            rows.append(
                {
                    columns[index]: row[index]
                    for index in range(min(len(columns), len(row)))
                }
            )
    return rows


def _counter_from_rows(rows: Iterable[dict[str, object]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        name = str(row.get(key, "")).strip()
        if not name:
            continue
        counter[name] += _to_int(row.get("count", 0))
    return dict(counter)


def _row_to_record(row: dict[str, object]) -> ObservabilityLogRecord:
    application = _normalize_application(row.get("application"))
    level = _normalize_level(row.get("level"))
    source = _normalize_source(row.get("source"))
    success_value = row.get("success")
    duration_value = row.get("duration_ms")

    return ObservabilityLogRecord(
        timestamp=str(row.get("timestamp", "")),
        application=application,
        level=level,
        source=source,
        message=str(row.get("message", "")),
        operation_id=str(row.get("operation_id", "")),
        request_id=str(row.get("request_id", "")),
        operation_name=str(row.get("operation_name", "")),
        result_code=str(row.get("result_code", "")),
        success=bool(success_value) if success_value is not None else None,
        duration_ms=_to_optional_float(duration_value),
        exception_type=str(row.get("exception_type", "")),
        problem_id=str(row.get("problem_id", "")),
    )


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return int(str(value))


def _to_optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _normalize_application(value: object) -> ApplicationName:
    normalized = str(value or "api").strip().lower()
    if normalized == "document_processor":
        return "document_processor"
    if normalized == "laws_collector":
        return "laws_collector"
    return "api"


def _normalize_level(value: object) -> LogLevel:
    normalized = str(value or "info").strip().lower()
    if normalized == "debug":
        return "debug"
    if normalized == "warning":
        return "warning"
    if normalized == "error":
        return "error"
    if normalized == "critical":
        return "critical"
    return "info"


def _normalize_source(value: object) -> LogSource:
    normalized = str(value or "trace").strip().lower()
    if normalized == "exception":
        return "exception"
    if normalized == "request":
        return "request"
    return "trace"


def _read_http_error_detail(exc: HTTPError) -> str:
    try:
        payload = exc.read().decode("utf-8")
    except Exception:
        return exc.reason or ""

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload.strip()

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            code = str(error.get("code", "")).strip()
            message = str(error.get("message", "")).strip()
            return " ".join(part for part in (code, message) if part)
    return payload.strip()


_UNION_QUERY = """
let traces = AppTraces
| extend app_role = tolower(tostring(column_ifexists("AppRoleName", column_ifexists("cloud_RoleName", ""))))
| extend severity = toint(column_ifexists("SeverityLevel", column_ifexists("severityLevel", 1)))
| project
    timestamp = TimeGenerated,
    application = case(
        app_role == "aijuristiction-api", "api",
        app_role == "document-processor", "document_processor",
        app_role == "laws-collector", "laws_collector",
        app_role
    ),
    level = case(
        severity >= 4, "critical",
        severity == 3, "error",
        severity == 2, "warning",
        severity == 1, "info",
        "debug"
    ),
    source = "trace",
    message = tostring(column_ifexists("Message", column_ifexists("message", ""))),
    operation_id = tostring(column_ifexists("OperationId", "")),
    request_id = tostring(column_ifexists("RequestId", "")),
    operation_name = tostring(column_ifexists("OperationName", "")),
    result_code = "",
    success = bool(null),
    duration_ms = real(null),
    exception_type = "",
    problem_id = "";
let exceptions = AppExceptions
| extend app_role = tolower(tostring(column_ifexists("AppRoleName", column_ifexists("cloud_RoleName", ""))))
| extend severity = toint(column_ifexists("SeverityLevel", column_ifexists("severityLevel", 3)))
| project
    timestamp = TimeGenerated,
    application = case(
        app_role == "aijuristiction-api", "api",
        app_role == "document-processor", "document_processor",
        app_role == "laws-collector", "laws_collector",
        app_role
    ),
    level = case(
        severity >= 4, "critical",
        severity == 3, "error",
        severity == 2, "warning",
        severity == 1, "info",
        "error"
    ),
    source = "exception",
    message = tostring(coalesce(
        column_ifexists("OuterMessage", ""),
        column_ifexists("InnermostMessage", ""),
        column_ifexists("Message", ""),
        column_ifexists("ProblemId", "")
    )),
    operation_id = tostring(column_ifexists("OperationId", "")),
    request_id = tostring(column_ifexists("RequestId", "")),
    operation_name = tostring(column_ifexists("OperationName", "")),
    result_code = "",
    success = bool(null),
    duration_ms = real(null),
    exception_type = tostring(column_ifexists("ExceptionType", "")),
    problem_id = tostring(column_ifexists("ProblemId", ""));
let requests = AppRequests
| extend app_role = tolower(tostring(column_ifexists("AppRoleName", column_ifexists("cloud_RoleName", ""))))
| extend request_success = tobool(column_ifexists("Success", true))
| project
    timestamp = TimeGenerated,
    application = case(
        app_role == "aijuristiction-api", "api",
        app_role == "document-processor", "document_processor",
        app_role == "laws-collector", "laws_collector",
        app_role
    ),
    level = iff(request_success, "info", "error"),
    source = "request",
    message = tostring(column_ifexists("Name", "")),
    operation_id = tostring(column_ifexists("OperationId", "")),
    request_id = tostring(column_ifexists("Id", "")),
    operation_name = tostring(column_ifexists("OperationName", column_ifexists("Name", ""))),
    result_code = tostring(column_ifexists("ResultCode", "")),
    success = request_success,
    duration_ms = todouble(column_ifexists("DurationMs", 0.0)),
    exception_type = "",
    problem_id = "";
union traces, exceptions, requests
| where application in ("api", "document_processor", "laws_collector")
""".strip()
