param([string]$Python = 'python', [string]$Rscript = 'Rscript', [string]$RunId = ('demo_' + (Get-Date -Format 'yyyyMMdd_HHmmss')))
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($Rscript -ne 'Rscript') {
        $rCommand = Get-Command $Rscript -ErrorAction Stop
        $env:PATH = (Split-Path -Parent $rCommand.Source) + [IO.Path]::PathSeparator + $env:PATH
    }
    & $Python -m drt_toolkit all --config config/demo.json --run-id $RunId
    if ($LASTEXITCODE -ne 0) { throw 'Demo failed. Inspect outputs/<run-id>/manifest.json and the stage console logs.' }
} finally { Pop-Location }
