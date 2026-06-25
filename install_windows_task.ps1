param(
    [int]$IntervalMinutes = 10
)

$ErrorActionPreference = "Stop"

$TaskName = "BiliHotwordsCollector"
$RunScript = Join-Path $PSScriptRoot "run_once.ps1"
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Collect Bilibili hot search keywords and build a daily report." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
