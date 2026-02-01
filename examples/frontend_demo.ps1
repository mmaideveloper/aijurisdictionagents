param(
    [string]$Root = "."
)

Set-Location $Root
Set-Location "frontend/aijurisdictionfronend"

if (-not (Test-Path "node_modules")) {
    npm install
}

npm run dev
