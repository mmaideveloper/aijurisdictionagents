param(
    [string]$Root = "."
)

Set-Location $Root
Set-Location "frontend/aijurisdictionfronend"

if (-not (Test-Path ".env")) {
    Write-Host "Tip: copy .env.example to .env to enable Azure Speech for the avatar demo."
}

if (-not (Test-Path "node_modules")) {
    npm install
}

npm run dev
