$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\nex.exe run app.nex --allow-read config\app.conf -- @args
exit $LASTEXITCODE
