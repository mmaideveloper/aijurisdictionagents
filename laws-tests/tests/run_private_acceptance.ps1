param([int]$Instance=924,[int]$DatabasePort=5494)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
$python = Join-Path $root 'conda/python.exe'
if ($env:LAWS_TEST_E2E_PYTHON) { $python = $env:LAWS_TEST_E2E_PYTHON }
foreach ($port in @(8940,8941)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is occupied; use an isolated acceptance run."
    }
}
foreach ($profile in @('codex-agent','laws-tests-dev')) {
    & ./scripts/sync_env_profile.ps1 -Mode Pull -Profile $profile
    if ($LASTEXITCODE -ne 0) { throw 'Profile synchronization failed.' }
}
$env:PYTHONPATH = "$root/laws-tests/api;$root/src"
$env:LOCAL_LLM_IO_LOGGING = '0'
& $python -m pip install -e 'laws-tests/api[test]'
if ($LASTEXITCODE -ne 0) { throw 'Tests dependencies unavailable.' }
& $python laws-tests/tests/setup_local.py --instance $Instance --port $DatabasePort --skip-account
if ($LASTEXITCODE -ne 0) { throw 'Isolated real PostgreSQL/model bootstrap failed.' }
& $python -m laws_tests.cli migrate
if ($LASTEXITCODE -ne 0) { throw 'Migration failed.' }
& $python -m laws_tests.cli seed-development
if ($LASTEXITCODE -ne 0) { throw 'Synthetic development seed failed.' }
& $python laws-tests/tests/private_fixture.py
if ($LASTEXITCODE -ne 0) { throw 'Synthetic fixture failed.' }
$processes = @()
try {
    $processes += Start-Process $python -ArgumentList @('-m','uvicorn','laws_tests.app:create_app','--factory','--host','127.0.0.1','--port','8941','--no-access-log') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/runs/issue924/api.out.log" -RedirectStandardError "$root/runs/issue924/api.err.log"
    $processes += Start-Process $python -ArgumentList @('-m','laws_tests.jobs') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/runs/issue924/worker.out.log" -RedirectStandardError "$root/runs/issue924/worker.err.log"
    Push-Location laws-tests/web
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependencies unavailable.' }
        $node = (Get-Command node).Source
        $processes += Start-Process $node -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','8940','--mode','private-e2e') -WorkingDirectory "$root/laws-tests/web" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/runs/issue924/web.out.log" -RedirectStandardError "$root/runs/issue924/web.err.log"
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try { $null = Invoke-WebRequest http://127.0.0.1:8940/api/health -TimeoutSec 2; $ready = $true; break }
            catch { Start-Sleep -Seconds 1 }
        }
        if (-not $ready) { throw 'Private-bank services did not become ready.' }
        npx playwright test --config private.playwright.config.ts
        if ($LASTEXITCODE -ne 0) { throw 'Real private-bank acceptance failed.' }
    } finally { Pop-Location }
} finally {
    foreach ($process in $processes) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    & $python laws-tests/tests/private_fixture.py cleanup
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic cleanup failed.' }
}
