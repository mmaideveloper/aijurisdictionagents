param(
    [Parameter(Mandatory = $true)]
    [int]$IssueNumber,

    [ValidateSet("Backlog", "Ready", "In progress", "In review", "Done")]
    [string]$Status = "In progress",

    [string]$Owner = "mmaideveloper",
    [int]$ProjectNumber = 5,
    [string]$Repo = "mmaideveloper/aijurisdictionagents",
    [string]$Comment
)

$project = gh project view $ProjectNumber --owner $Owner --format json | ConvertFrom-Json
$projectId = $project.id

$fields = gh project field-list $ProjectNumber --owner $Owner --format json | ConvertFrom-Json
$statusField = $fields.fields | Where-Object { $_.name -eq "Status" }
if (-not $statusField) {
    throw "Status field not found in project."
}

$option = $statusField.options | Where-Object { $_.name -eq $Status }
if (-not $option) {
    throw "Status option '$Status' not found."
}

$items = gh project item-list $ProjectNumber --owner $Owner --format json --limit 200 | ConvertFrom-Json
$item = $items.items | Where-Object { $_.content.number -eq $IssueNumber }
if (-not $item) {
    throw "Issue #$IssueNumber not found in project."
}

$null = gh project item-edit `
    --id $item.id `
    --project-id $projectId `
    --field-id $statusField.id `
    --single-select-option-id $option.id

if ($Comment) {
    $null = gh issue comment $IssueNumber --repo $Repo --body $Comment
}

Write-Host "Updated issue #$IssueNumber to '$Status'."
if ($Comment) {
    Write-Host "Added comment: $Comment"
}
