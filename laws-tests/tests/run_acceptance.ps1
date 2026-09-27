$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
$python=Join-Path $root 'conda/python.exe'
if($env:LAWS_TEST_E2E_PYTHON){ $python=$env:LAWS_TEST_E2E_PYTHON }
if(-not(Test-Path $python)){ throw 'Prepare conda/python.exe or configure the trusted runner LAWS_TEST_E2E_PYTHON interpreter.' }
$env:LAWS_TEST_E2E_PYTHON=$python
foreach($port in @(8410,8411,8412,8413,8414)){
    if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){throw "Port $port is already in use; use an isolated runner."}
}
& ./scripts/sync_env_profile.ps1 -Mode Pull -Profile codex-agent
if($LASTEXITCODE -ne 0){throw 'Profile sync failed'}
$env:PYTHONPATH="$root/laws-tests/api;$root/src"
& ./scripts/sync_env_profile.ps1 -Mode Pull -Profile laws-tests-dev
if($LASTEXITCODE -ne 0){throw 'Laws-tests development profile sync failed'}
& $python laws-tests/tests/setup_local.py
if($LASTEXITCODE -ne 0){throw 'Local database/model bootstrap failed'}
$env:PYTHONPATH="$root/laws-tests/api;$root/src"
& $python -m laws_tests.cli migrate
if($LASTEXITCODE -ne 0){throw 'Migration failed'}
& $python -m laws_tests.cli seed-development
if($LASTEXITCODE -ne 0){throw 'Seed failed'}
& $python laws-tests/tests/reader_fixture.py
if($LASTEXITCODE -ne 0){throw 'Synthetic law reader seed failed'}
$env:NODE_USE_SYSTEM_CA='1'
foreach($project in @('laws-tests/web','frontend/aijurisdictionfronend')){
    Push-Location $project
    try { npm ci; if($LASTEXITCODE -ne 0){throw 'Frontend installation failed'} } finally { Pop-Location }
}
$processes=@()
try{
    foreach($service in @('tests','identity','mcp')){
        $processes+=Start-Process $python -ArgumentList @('laws-tests/tests/run_local_service.py',$service) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/runs/issue840/$service.out.log" -RedirectStandardError "$root/runs/issue840/$service.err.log"
    }
    $node=(Get-Command node).Source
    $processes+=Start-Process $node -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','8410') -WorkingDirectory "$root/laws-tests/web" -WindowStyle Hidden -PassThru
    $env:VITE_API_BASE_URL='http://127.0.0.1:8413'
    $env:VITE_LAWS_TEST_PUBLIC_URL='http://127.0.0.1:8410'
    $processes+=Start-Process $node -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','8412') -WorkingDirectory "$root/frontend/aijurisdictionfronend" -WindowStyle Hidden -PassThru
    $ready=$false
    for($i=0;$i -lt 120;$i++){
        try { $null=Invoke-WebRequest http://127.0.0.1:8413/health -TimeoutSec 5; $ready=$true; break } catch { Start-Sleep -Seconds 2 }
    }
    if(-not $ready){throw 'Identity API did not become ready'}
    Push-Location laws-tests/web
    try { npm run test:e2e; if($LASTEXITCODE -ne 0){throw 'Real E2E failed'} } finally {Pop-Location}
} finally {
    foreach($process in $processes){ Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    & $python laws-tests/tests/reader_fixture.py cleanup
    & $python laws-tests/tests/cleanup_acceptance.py
}
