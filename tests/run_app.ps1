$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$condaPrefix = Join-Path $repoRoot ".conda"
$env:CONDA_PREFIX = $condaPrefix
$env:PATH = "$condaPrefix;$condaPrefix\Scripts;$env:PATH"

$pythonExe = Join-Path $condaPrefix "python.exe"
$instruction = "We believe the contract was breached due to late delivery."
$caseId = [guid]::NewGuid().ToString()

& $pythonExe -m aijurisdictionagents `
  --country "SK" `
  --language "en" `
  --discussion-type "advice" `
  --discussion-max-minutes 15 `
  --question-timeout-minutes 5 `
  --log-level "DEBUG" `
  --data-dir (Join-Path $repoRoot "data") `
  --case-id $caseId `
  --instruction $instruction
