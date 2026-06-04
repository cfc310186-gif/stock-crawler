# External Scheduler Setup

Use an external scheduler to call GitHub `workflow_dispatch` at Taiwan time 19:30. GitHub Actions will still run the job, but GitHub no longer controls the exact trigger time.

## Prerequisite

Push the workflow that supports `target_date`:

```powershell
git push origin main
```

## GitHub Token

Create a fine-grained personal access token:

- Repository access: `cfc310186-gif/stock-crawler`
- Repository permission: `Actions` = `Read and write`
- Expiration: 90 or 180 days

Do not paste the token into chat or commit it to the repo. Store it in the external scheduler's secret field, or in local environment variable `GITHUB_DISPATCH_TOKEN` for manual tests.

## HTTP Request

URL:

```text
https://api.github.com/repos/cfc310186-gif/stock-crawler/actions/workflows/main.yml/dispatches
```

Method:

```text
POST
```

Headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer <GITHUB_TOKEN>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Body for normal daily run:

```json
{
  "ref": "main",
  "inputs": {
    "target_date": ""
  }
}
```

Body for a manual backfill:

```json
{
  "ref": "main",
  "inputs": {
    "target_date": "2026-06-03"
  }
}
```

## Schedule

Set the external scheduler timezone to `Asia/Taipei`.

Cron:

```text
30 19 * * 1-5
```

This means Monday to Friday at 19:30 Taiwan time.

## Local Dispatch Test

PowerShell:

```powershell
$env:GITHUB_DISPATCH_TOKEN = "<token>"
.\scripts\dispatch_daily_workflow.ps1
```

Backfill a specific date:

```powershell
$env:GITHUB_DISPATCH_TOKEN = "<token>"
.\scripts\dispatch_daily_workflow.ps1 -TargetDate "2026-06-03"
```

## Verification

Open:

```text
https://github.com/cfc310186-gif/stock-crawler/actions/workflows/main.yml
```

The run should show:

```text
event_name=workflow_dispatch
target_date=auto
run_started_taipei=...
```

The GitHub-native `schedule` trigger has been removed. The external scheduler is now the only automatic trigger, preventing duplicate same-day runs.
