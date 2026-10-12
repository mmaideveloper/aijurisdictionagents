param([string]$LokiUrl)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dashboard = Get-Content (Join-Path $root 'Deployment/monitoring/grafana/dashboards/jurisdigta-errors.json') -Raw | ConvertFrom-Json
$panel = $dashboard.panels | Where-Object id -eq 1
$query = $panel.targets[0].expr
if ($panel.datasource.uid -ne 'jurisdigta-loki' -or
    $panel.targets[0].queryType -ne 'instant' -or
    -not $query.Contains('[$__range]') -or
    $query.Contains('jurisdigta_errors_window')) {
    throw 'Total Errors must count Loki lines over the selected range at its end.'
}
$logs = Get-Content (Join-Path $root 'Deployment/monitoring/grafana/dashboards/jurisdigta-system-logs.json') -Raw | ConvertFrom-Json
$filter = (($logs.panels | Where-Object title -eq 'Errors Only').targets[0].expr -split ' \|~ ')[1]
if (-not $query.Contains($filter)) { throw 'Operational failure filter differs from System Logs.' }
$end = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString() + '000000'
foreach ($window in @('5m', '6h')) {
    $resolved = $query.Replace('$__range', $window)
    if ($LokiUrl) {
        $url = $LokiUrl.TrimEnd('/') + '/loki/api/v1/query?query=' + [Uri]::EscapeDataString($resolved) + '&time=' + $end
        $result = Invoke-RestMethod $url
        if ($result.status -ne 'success') { throw 'Loki query failed.' }
        $values = @($result.data.result)
        $count = if ($values.Count) { $values[0].value[1] } else { 'No matching data' }
        Write-Output "$window : $count"
    } else {
        Write-Output "$window : selected-range query contract passed"
    }
}
Write-Output 'PASS: shared failure filter, selected range, instant evaluation.'
