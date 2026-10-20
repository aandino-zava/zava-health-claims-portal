$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'work/uv-cache' }
    $env:ENVIRONMENT = 'development'
    $env:AUTH_MODE = 'development'
    if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'sqlite:///./claims.db' }
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    uv run python -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic seed failed' }
    Write-Output 'Open http://127.0.0.1:8000. Press Ctrl+C to stop.'
    uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
} finally { Pop-Location }
