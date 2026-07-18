# Gemini 要約パイプライン（既定: gemini-3.5-flash + thinking low → app_gemini01/.env）
# 使い方: .\run_pipeline.ps1
#         .\run_pipeline.ps1 "https://www.youtube.com/watch?v=動画ID"
param(
    [string]$Url = "https://www.youtube.com/watch?v=koBLOf-53_g"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\app_gemini01

Write-Host "=== Gemini 要約パイプライン (3.5-flash) ===" -ForegroundColor Cyan
python scripts/run_pipeline.py $Url --provider gemini --model gemini-3.5-flash --thinking-level low
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "ログは app_gemini01\logs\ に保存されています" -ForegroundColor Green

Set-Location $PSScriptRoot
