param(
    [string]$TargetDate = "",
    [string]$Owner = "cfc310186-gif",
    [string]$Repo = "stock-crawler",
    [string]$Workflow = "main.yml",
    [string]$Ref = "main"
)

$ErrorActionPreference = "Stop"

$token = $env:GITHUB_DISPATCH_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Error "Set GITHUB_DISPATCH_TOKEN before running this script."
}

if (-not [string]::IsNullOrWhiteSpace($TargetDate)) {
    try {
        [datetime]::ParseExact($TargetDate, "yyyy-MM-dd", $null) | Out-Null
    }
    catch {
        Write-Error "TargetDate must use YYYY-MM-DD, got '$TargetDate'."
    }
}

$uri = "https://api.github.com/repos/$Owner/$Repo/actions/workflows/$Workflow/dispatches"
$body = @{
    ref = $Ref
    inputs = @{
        target_date = $TargetDate
    }
} | ConvertTo-Json -Depth 4

$headers = @{
    Accept = "application/vnd.github+json"
    Authorization = "Bearer $token"
    "X-GitHub-Api-Version" = "2022-11-28"
}

Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body

$displayDate = if ([string]::IsNullOrWhiteSpace($TargetDate)) { "auto" } else { $TargetDate }
Write-Host "Dispatched $Owner/$Repo $Workflow on $Ref with target_date=$displayDate"
