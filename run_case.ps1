param([string]$Python='python',[string]$Rscript='Rscript',[string]$RunId=('case_'+(Get-Date -Format 'yyyyMMdd_HHmmss')),[string]$Config='config/case_study.json')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    if ($Rscript -ne 'Rscript') {
        $taskR=Get-Command $Rscript -ErrorAction Stop
        $env:PATH=(Split-Path -Parent $taskR.Source)+[IO.Path]::PathSeparator+$env:PATH
    }
    & $Python -m drt_toolkit all --config $Config --run-id $RunId
    if ($LASTEXITCODE -ne 0) { throw 'Study run failed. Inspect the run manifest and stage logs.' }
} finally { Pop-Location }
