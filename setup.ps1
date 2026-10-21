param([string]$Python = 'python', [string]$Rscript = 'Rscript')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    & $Rscript -e 'p <- c("jsonlite","AER","mgcv"); q <- p[!vapply(p,requireNamespace,logical(1),quietly=TRUE)]; if(length(q)) install.packages(q,repos="https://cloud.r-project.org")'
    if ($LASTEXITCODE -ne 0) { throw 'R dependency installation failed' }
} finally { Pop-Location }
