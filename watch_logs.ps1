# Скрипт для просмотра логов бота в реальном времени
# Encoding: UTF-8
param(
    [int]$Tail = 50,
    [string]$LogFile = "logs/bot.log"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "Просмотр логов бота в реальном времени..." -ForegroundColor Green
Write-Host "Файл: $LogFile" -ForegroundColor Cyan
Write-Host "Последние $Tail строк" -ForegroundColor Cyan
Write-Host "Для выхода нажмите Ctrl+C" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $LogFile)) {
    Write-Host "Файл $LogFile не найден. Ожидание создания файла..." -ForegroundColor Yellow
    while (-not (Test-Path $LogFile)) {
        Start-Sleep -Seconds 1
    }
    Write-Host "Файл найден, начинаем просмотр..." -ForegroundColor Green
    Write-Host ""
}

try {
    Get-Content -Path $LogFile -Wait -Tail $Tail -Encoding UTF8
} catch {
    Write-Host "Ошибка при чтении файла: $_" -ForegroundColor Red
    exit 1
}
