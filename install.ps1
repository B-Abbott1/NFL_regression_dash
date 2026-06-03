# Install dependencies into the project venv (.venv).
# Run from project root:  .\install.ps1

$ErrorActionPreference = "Stop"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv ..."
    python -m venv (Join-Path $PSScriptRoot ".venv")
}

Write-Host "Upgrading pip ..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing core packages (wheels only) ..."
& $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host "Installing nfl-data-py without dependency pins (numpy<2 / pandas<2 conflict) ..."
& $venvPython -m pip install "nfl-data-py==0.3.3" --no-deps

Write-Host "Done. Activate with:  .venv\Scripts\Activate.ps1"
