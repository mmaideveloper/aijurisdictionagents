[CmdletBinding()]
param(
    [string]$EnvExamplePath = ".env.example",
    [string]$EnvPath = ".env",
    [string]$UnknownValue = "unknown-variable",
    [string]$SshSourceDir = "E:\jurisdigta\ssh",
    [string]$SshTargetDir = (Join-Path $HOME ".ssh\jurisdigta"),
    [string]$SshPublicKeyPath,
    [string]$ServerAlias = "jurisdigta-server",
    [string]$RemoteEnvPath = "/srv/jurisdigta/secrets/jurisdigta.env",
    [switch]$SkipSshKeySync,
    [switch]$SkipTransfer,
    [switch]$UseSudo,
    [switch]$AcceptNewHostKey,
    [switch]$AllowLegacyPush,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    $scriptRoot = Split-Path -Parent $PSCommandPath
    $repoRoot = Split-Path -Parent $scriptRoot
    return Join-Path $repoRoot $Path
}

function Assert-ToolInstalled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ToolName
    )

    if (-not (Get-Command $ToolName -ErrorAction SilentlyContinue)) {
        throw "Missing required tool '$ToolName'. Install it and retry."
    }
}

function ConvertTo-SingleQuotedShellValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Get-EnvKeysFromExample {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -Path $Path)) {
        throw "Env example file not found: $Path"
    }

    $keys = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)=.*$") {
            $key = $Matches[1]
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $keys.Add($key)
            }
        }
    }

    return $keys
}

function Get-ActiveEnvValues {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $values = @{}
    if (-not (Test-Path -Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }

    return $values
}

function Update-LocalEnvFromExample {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExamplePath,
        [Parameter(Mandatory = $true)]
        [string]$LocalEnvPath,
        [Parameter(Mandatory = $true)]
        [string]$PlaceholderValue,
        [Parameter(Mandatory = $true)]
        [bool]$PreviewOnly
    )

    $exampleKeys = Get-EnvKeysFromExample -Path $ExamplePath
    $activeValues = Get-ActiveEnvValues -Path $LocalEnvPath
    $missingKeys = @($exampleKeys | Where-Object { -not $activeValues.ContainsKey($_) })

    if ($missingKeys.Count -eq 0) {
        Write-Host "Local .env already contains every key from .env.example."
        return $missingKeys
    }

    Write-Warning ("Missing local .env keys: " + ($missingKeys -join ", "))

    if ($PreviewOnly) {
        Write-Host "Dry run: local .env was not changed."
        return $missingKeys
    }

    if (-not (Test-Path -Path $LocalEnvPath)) {
        New-Item -ItemType File -Path $LocalEnvPath -Force | Out-Null
    }

    $existingContent = Get-Content -Path $LocalEnvPath -Raw
    $separator = ""
    if (-not [string]::IsNullOrEmpty($existingContent) -and -not $existingContent.EndsWith("`n")) {
        $separator = "`r`n"
    }

    $linesToAppend = New-Object System.Collections.Generic.List[string]
    $linesToAppend.Add("")
    $linesToAppend.Add("# Added from .env.example by scripts/sync_jurisdigta_env.ps1.")
    foreach ($key in $missingKeys) {
        $linesToAppend.Add("$key=$PlaceholderValue")
    }

    Add-Content -Path $LocalEnvPath -Value ($separator + ($linesToAppend -join "`r`n"))
    Write-Host "Added $($missingKeys.Count) missing key(s) to local .env with value '$PlaceholderValue'."
    return $missingKeys
}

function Sync-SshKeyFolder {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDir,
        [Parameter(Mandatory = $true)]
        [string]$TargetDir,
        [string]$PublicKeyPath,
        [Parameter(Mandatory = $true)]
        [bool]$PreviewOnly
    )

    if (-not (Test-Path -Path $SourceDir)) {
        Write-Warning "SSH source directory not found: $SourceDir"
        return $null
    }

    $publicKey = $null
    if (-not [string]::IsNullOrWhiteSpace($PublicKeyPath)) {
        $publicKey = Get-Item -Path $PublicKeyPath
    } else {
        $publicKeys = @(Get-ChildItem -Path $SourceDir -Filter "*.pub" -File | Sort-Object Name)
        if ($publicKeys.Count -eq 0) {
            Write-Warning "No *.pub file found in $SourceDir"
            return $null
        }
        if ($publicKeys.Count -gt 1) {
            throw "Multiple *.pub files found in $SourceDir. Pass -SshPublicKeyPath to select one."
        }
        $publicKey = $publicKeys[0]
    }

    $privateKeyPath = $publicKey.FullName.Substring(0, $publicKey.FullName.Length - 4)
    $privateKey = $null
    if (Test-Path -Path $privateKeyPath) {
        $privateKey = Get-Item -Path $privateKeyPath
    }

    Write-Host "Selected SSH public key: $($publicKey.FullName)"
    if ($privateKey) {
        Write-Host "Matching private key will be copied to the dedicated local SSH folder."
    } else {
        Write-Warning "Matching private key was not found next to the public key. SSH transfer will use the configured alias/default agent."
    }

    if ($PreviewOnly) {
        Write-Host "Dry run: SSH key folder was not changed."
        $configPath = Join-Path $TargetDir "config"
        if ($privateKey) {
            return [pscustomobject]@{
                PrivateKeyPath = (Join-Path $TargetDir $privateKey.Name)
                ConfigPath = $configPath
            }
        }
        return [pscustomobject]@{
            PrivateKeyPath = $null
            ConfigPath = $configPath
        }
    }

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    if (Get-Command icacls -ErrorAction SilentlyContinue) {
        & icacls $TargetDir /inheritance:r /grant:r "${identity}:(OI)(CI)F" | Out-Null
    }

    Copy-Item -Path $publicKey.FullName -Destination (Join-Path $TargetDir $publicKey.Name) -Force

    $targetPrivateKey = $null
    if ($privateKey) {
        $targetPrivateKey = Join-Path $TargetDir $privateKey.Name
        if ((Test-Path -Path $targetPrivateKey) -and (Get-Command icacls -ErrorAction SilentlyContinue)) {
            & icacls $targetPrivateKey /inheritance:r /grant:r "${identity}:F" | Out-Null
        }
        Copy-Item -Path $privateKey.FullName -Destination $targetPrivateKey -Force
    }

    $targetConfigPath = $null
    $sourceConfigPath = Join-Path $SourceDir "config"
    if (Test-Path -Path $sourceConfigPath) {
        $targetConfigPath = Join-Path $TargetDir "config"
        if ((Test-Path -Path $targetConfigPath) -and (Get-Command icacls -ErrorAction SilentlyContinue)) {
            & icacls $targetConfigPath /inheritance:r /grant:r "${identity}:F" | Out-Null
        }
        Copy-Item -Path $sourceConfigPath -Destination $targetConfigPath -Force
    }

    if (Get-Command icacls -ErrorAction SilentlyContinue) {
        & icacls $TargetDir /inheritance:r /grant:r "${identity}:(OI)(CI)F" | Out-Null
        if ($targetPrivateKey) {
            & icacls $targetPrivateKey /inheritance:r /grant:r "${identity}:R" | Out-Null
        }
        if ($targetConfigPath) {
            & icacls $targetConfigPath /inheritance:r /grant:r "${identity}:R" | Out-Null
        }
    }

    Write-Host "Dedicated SSH folder is ready: $TargetDir"
    return [pscustomobject]@{
        PrivateKeyPath = $targetPrivateKey
        ConfigPath = $targetConfigPath
    }
}

function Publish-EnvToServer {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LocalEnvPath,
        [Parameter(Mandatory = $true)]
        [string]$HostAlias,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [string]$PrivateKeyPath,
        [string]$ConfigPath,
        [Parameter(Mandatory = $true)]
        [bool]$TrustNewHostKey,
        [Parameter(Mandatory = $true)]
        [bool]$InstallWithSudo,
        [Parameter(Mandatory = $true)]
        [bool]$PreviewOnly
    )

    if (-not (Test-Path -Path $LocalEnvPath)) {
        throw "Local .env file not found: $LocalEnvPath"
    }

    $remoteDir = $TargetPath.Substring(0, $TargetPath.LastIndexOf("/"))
    $remoteUpload = "jurisdigta.env.upload"
    $sshArgs = @("-o", "BatchMode=yes")
    if ($TrustNewHostKey) {
        $sshArgs += @("-o", "StrictHostKeyChecking=accept-new")
    }
    if (-not [string]::IsNullOrWhiteSpace($ConfigPath) -and (Test-Path -Path $ConfigPath)) {
        $sshArgs += @("-F", $ConfigPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($PrivateKeyPath) -and (Test-Path -Path $PrivateKeyPath)) {
        $sshArgs += @("-i", $PrivateKeyPath)
    }

    $installPrefix = ""
    if ($InstallWithSudo) {
        $installPrefix = "sudo "
    }

    $quotedRemoteDir = ConvertTo-SingleQuotedShellValue -Value $remoteDir
    $quotedRemoteUpload = ConvertTo-SingleQuotedShellValue -Value $remoteUpload
    $quotedTargetPath = ConvertTo-SingleQuotedShellValue -Value $TargetPath
    $installCommand = "${installPrefix}install -d -m 700 $quotedRemoteDir && ${installPrefix}install -m 600 $quotedRemoteUpload $quotedTargetPath && rm -f $quotedRemoteUpload && stat -c '%a %U %G %n' $quotedTargetPath"

    Write-Host "Publishing local .env to ${HostAlias}:$TargetPath"
    if ($PreviewOnly) {
        Write-Host "Dry run: no SSH or SCP transfer was performed."
        return
    }

    Assert-ToolInstalled -ToolName "ssh"
    Assert-ToolInstalled -ToolName "scp"

    $localTransferPath = Join-Path ([System.IO.Path]::GetTempPath()) ("jurisdigta.env." + [System.Guid]::NewGuid().ToString("N"))
    $localEnvContent = [System.IO.File]::ReadAllText($LocalEnvPath)
    $normalizedEnvContent = $localEnvContent.Replace("`r`n", "`n").Replace("`r", "`n")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($localTransferPath, $normalizedEnvContent, $utf8NoBom)

    & ssh @sshArgs $HostAlias "umask 077 && touch $quotedRemoteUpload && chmod 600 $quotedRemoteUpload"
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Path $localTransferPath -Force -ErrorAction SilentlyContinue
        throw "Failed to prepare remote upload file on $HostAlias."
    }

    & scp @sshArgs $localTransferPath "${HostAlias}:$remoteUpload"
    Remove-Item -Path $localTransferPath -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy local .env to $HostAlias."
    }

    & ssh @sshArgs $HostAlias $installCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install remote env file at $TargetPath."
    }
}

$resolvedEnvExamplePath = Resolve-RepoPath -Path $EnvExamplePath
$resolvedEnvPath = Resolve-RepoPath -Path $EnvPath

$null = Update-LocalEnvFromExample `
    -ExamplePath $resolvedEnvExamplePath `
    -LocalEnvPath $resolvedEnvPath `
    -PlaceholderValue $UnknownValue `
    -PreviewOnly ([bool]$DryRun)

$activeEnvValues = Get-ActiveEnvValues -Path $resolvedEnvPath
$unknownKeys = @($activeEnvValues.Keys | Sort-Object | Where-Object { $activeEnvValues[$_] -eq $UnknownValue })
if ($unknownKeys.Count -gt 0) {
    Write-Warning ("Local .env still contains '$UnknownValue' for: " + ($unknownKeys -join ", "))
}

$privateKeyPathForTransfer = $null
$configPathForTransfer = $null
if (-not $SkipSshKeySync) {
    $sshMaterial = Sync-SshKeyFolder `
        -SourceDir $SshSourceDir `
        -TargetDir $SshTargetDir `
        -PublicKeyPath $SshPublicKeyPath `
        -PreviewOnly ([bool]$DryRun)
    if ($sshMaterial) {
        $privateKeyPathForTransfer = $sshMaterial.PrivateKeyPath
        $configPathForTransfer = $sshMaterial.ConfigPath
    }
}

if (-not $SkipTransfer) {
    if (-not $AllowLegacyPush) {
        throw "Legacy laptop-to-server .env push is disabled. Use scripts/sync_env_profile.ps1 -Mode Pull. Pass -AllowLegacyPush only for an explicitly approved emergency migration."
    }
    Publish-EnvToServer `
        -LocalEnvPath $resolvedEnvPath `
        -HostAlias $ServerAlias `
        -TargetPath $RemoteEnvPath `
        -PrivateKeyPath $privateKeyPathForTransfer `
        -ConfigPath $configPathForTransfer `
        -TrustNewHostKey ([bool]$AcceptNewHostKey) `
        -InstallWithSudo ([bool]$UseSudo) `
        -PreviewOnly ([bool]$DryRun)
}

Write-Host "JurisDigta env sync completed."
