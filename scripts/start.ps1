# 本地一条命令启动服务
# 用法：.\scripts\start.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "找不到 .venv，先执行：" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "找不到 .env，先复制模板并填入密钥：" -ForegroundColor Red
    Write-Host "  Copy-Item .env.example .env"
    exit 1
}

if (-not (Test-Path "data\retail.db")) {
    Write-Host "找不到 data\retail.db，先生成数据：" -ForegroundColor Yellow
    Write-Host "  $python scripts\generate_data.py"
    exit 1
}

Write-Host "启动中：http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "接口文档：http://127.0.0.1:8000/docs" -ForegroundColor DarkGray
Write-Host "按 Ctrl+C 停止" -ForegroundColor DarkGray

& $python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
