$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& .\.venv\Scripts\python.exe -c "import importlib.util, sys; sys.exit(not all(importlib.util.find_spec(m) for m in ('fastapi', 'uvicorn', 'cryptography', 'jwt')))"
if ($LASTEXITCODE -ne 0) {
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the required packages.' }
}
& .\.venv\Scripts\python.exe run.py
