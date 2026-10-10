# Synthetic arithmetic only. This script does not enable application scoring.
$ErrorActionPreference = 'Stop'
function Get-CandidateScore {
    param([bool]$Approved, [bool]$CriticalFailure, [decimal[]]$Components)
    if (-not $Approved) { return @{ status='pending_policy_approval'; score=$null } }
    if ($CriticalFailure) { return @{ status='blocked'; score=$null } }
    if ($Components.Count -ne 4) { return @{ status='incomplete'; score=$null } }
    foreach ($component in $Components) {
        if ($component -lt 0 -or $component -gt 100) { throw 'Out-of-scale synthetic component' }
    }
    $candidate = [decimal]::Round(($Components[0]*40 + $Components[1]*30 + $Components[2]*20 + $Components[3]*10)/100, 2, [MidpointRounding]::AwayFromZero)
    return @{ status='synthetic_proposal_only'; score=$candidate }
}
$pending = Get-CandidateScore -Approved $false -CriticalFailure $false -Components @(100,100,100,100)
$blocked = Get-CandidateScore -Approved $true -CriticalFailure $true -Components @(100,100,100,100)
$missing = Get-CandidateScore -Approved $true -CriticalFailure $false -Components @(100,100)
$complete = Get-CandidateScore -Approved $true -CriticalFailure $false -Components @(90,80,100,70)
if ($null -ne $pending.score -or $null -ne $blocked.score -or $null -ne $missing.score -or $complete.score -ne 87) { throw 'Synthetic proposal assertion failed' }
@{ policy='response-quality/1-draft'; application_scoring_enabled=$false; fixtures=@($pending,$blocked,$missing,$complete) } | ConvertTo-Json -Depth 4
