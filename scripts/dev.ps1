param(
    [ValidateSet("help", "setup", "test", "lint", "format", "migrate", "evaluate", "learn-model", "advanced-learn", "walk-forward", "import-walk-forward", "verify", "run")]
    [string]$Command = "help",
    [switch]$SkipBrowser,
    [int]$Months = 2,
    [int]$Count = 1,
    [int]$RandomSamples = 200,
    [string]$Report,
    [int]$Numbers3Tickets = 5,
    [string]$Lottery,
    [switch]$ReplaceExisting,
    [int]$Loops = 5
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Get-ProjectPython {
    if (Test-Path -LiteralPath $VenvPython) {
        return $VenvPython
    }
    return "python"
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $python = Get-ProjectPython
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Lint {
    Invoke-Python -m ruff check app scripts tests migrations
    if (Get-Command node -ErrorAction SilentlyContinue) {
        & node --check app\static\js\app.js
        if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed" }
    }
}

function Invoke-MigrationVerification {
    $cacheDir = Join-Path $ProjectRoot ".pytest_cache"
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
    $testDb = [System.IO.Path]::GetFullPath((Join-Path $cacheDir "migration-verification.db"))
    $allowedRoot = [System.IO.Path]::GetFullPath($cacheDir) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $testDb.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe migration test path: $testDb"
    }
    if (Test-Path -LiteralPath $testDb) { Remove-Item -LiteralPath $testDb -Force }
    $previousDbPath = $env:LOTTERY_DB_PATH
    try {
        $env:LOTTERY_DB_PATH = $testDb
        Invoke-Python -m alembic upgrade head
        Invoke-Python scripts\verify_database.py $testDb
    }
    finally {
        $env:LOTTERY_DB_PATH = $previousDbPath
        if (Test-Path -LiteralPath $testDb) { Remove-Item -LiteralPath $testDb -Force }
    }
}

Set-Location $ProjectRoot

switch ($Command) {
    "setup" {
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv" }
        }
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            & uv pip install --python $VenvPython -r requirements-dev.txt
            if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
        }
        else {
            Invoke-Python -m pip install -r requirements-dev.txt
        }
        if (-not $SkipBrowser) {
            Invoke-Python -m playwright install chromium
        }
    }
    "test" {
        Invoke-Python -m pytest -q
    }
    "lint" {
        Invoke-Lint
    }
    "format" {
        Invoke-Python -m ruff format app scripts tests migrations
        Invoke-Python -m ruff check app scripts tests migrations --fix
    }
    "migrate" {
        Invoke-Python -m alembic upgrade head
    }
    "evaluate" {
        Invoke-Python -m alembic upgrade head
        Invoke-Python scripts\evaluate_model.py
    }
    "learn-model" {
        if (-not $Report) { throw "-Report に評価JSONのパスを指定してください" }
        Invoke-Python -m alembic upgrade head
        Invoke-Python scripts\learn_model.py $Report
    }
    "advanced-learn" {
        Invoke-Python -m alembic upgrade head
        Invoke-Python scripts\advanced_train_model.py --loops $Loops
    }
    "walk-forward" {
        Invoke-Python -m alembic upgrade head
        if ($Lottery) {
            Invoke-Python scripts\walk_forward_evaluate.py --months $Months --count $Count --random-samples $RandomSamples --lottery $Lottery
        }
        else {
            Invoke-Python scripts\walk_forward_evaluate.py --months $Months --count $Count --random-samples $RandomSamples
        }
    }
    "import-walk-forward" {
        if (-not $Report) { throw "-Report に評価JSONのパスを指定してください" }
        Invoke-Python -m alembic upgrade head
        if ($ReplaceExisting) {
            Invoke-Python scripts\import_walk_forward_results.py $Report --numbers3-tickets $Numbers3Tickets --replace-existing
        }
        else {
            Invoke-Python scripts\import_walk_forward_results.py $Report --numbers3-tickets $Numbers3Tickets
        }
    }
    "verify" {
        Invoke-Lint
        Invoke-MigrationVerification
        Invoke-Python -m pytest -q
        Invoke-Python -m compileall -q app scripts tests migrations
    }
    "run" {
        Invoke-Python scripts\run_server.py
    }
    default {
        Write-Host "Usage: .\scripts\dev.ps1 <command>"
        Write-Host "  setup    Create .venv and install development dependencies"
        Write-Host "  test     Run all tests"
        Write-Host "  lint     Run Python and JavaScript checks"
        Write-Host "  format   Format code and apply safe Ruff fixes"
        Write-Host "  migrate  Upgrade the configured database to the latest revision"
        Write-Host "  evaluate Evaluate and save model metrics for new draw data"
        Write-Host "  learn-model Learn Numbers3 weights from a walk-forward report"
        Write-Host "  advanced-learn Repeat loss feedback learning and verify on untouched data"
        Write-Host "  walk-forward Simulate predictions against the latest held-out draws"
        Write-Host "  import-walk-forward Add a report's predictions to the purchase ledger"
        Write-Host "  verify   Run lint, migration verification, tests, and compilation"
        Write-Host "  run      Migrate and start the local server"
    }
}
