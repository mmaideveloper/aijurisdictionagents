$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$condaPrefix = Join-Path $repoRoot ".conda"
$env:CONDA_PREFIX = $condaPrefix
$env:PATH = "$condaPrefix;$condaPrefix\Scripts;$env:PATH"

$pythonExe = Join-Path $condaPrefix "python.exe"
$instruction = "Chcem získať právnu radu ohľadom prenájmu bytu v Slovenskej republike."
$caseId = [guid]::NewGuid().ToString()

# Run the AI Jurisdiction Agents application with specified parameters
# --data-dir (Join-Path $repoRoot "data") `
& $pythonExe -m aijurisdictionagents `
  --country "SK" `
  --language "sk" `
  --discussion-type "advice" `
  --discussion-max-minutes 15 `
  --question-timeout-minutes 5 `
  --log-level "DEBUG" `
  --data-dir None `
  --case-id $caseId `
  --instruction $instruction
