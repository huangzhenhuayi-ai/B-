$ErrorActionPreference = "Stop"

$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $BundledPython) {
    $Python = $BundledPython
} else {
    $Python = "python"
}

$Script = Join-Path $PSScriptRoot "dashboard.py"

& $Python $Script --host 127.0.0.1 --port 8765 --open
