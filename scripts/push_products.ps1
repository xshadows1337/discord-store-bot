# Reads bot_api_url and bot_api_secret from src/settings.json
# then PUTs src/products.json to the live bot.

$root = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $root "src\settings.json"
$productsPath = Join-Path $root "src\products.json"

if (-not (Test-Path $settingsPath)) {
    Write-Host "ERROR: src/settings.json not found." -ForegroundColor Red
    exit 1
}

$settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
$url    = $settings.bot_api_url
$secret = $settings.bot_api_secret

if (-not $url -or $url -eq "https://YOUR-RAILWAY-URL.up.railway.app") {
    Write-Host ""
    Write-Host "  Set bot_api_url in src/settings.json to your Railway public domain." -ForegroundColor Yellow
    Write-Host "  Example: https://empowering-exploration.up.railway.app" -ForegroundColor DarkGray
    Write-Host ""
    exit 1
}

if (-not $secret -or $secret -eq "change-me-to-a-strong-random-secret") {
    Write-Host ""
    Write-Host "  Set bot_api_secret in src/settings.json (and BOT_API_SECRET in Railway env vars)." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$body = [System.IO.File]::ReadAllBytes($productsPath)

$headers = @{
    "Authorization" = "Bearer $secret"
    "Content-Type"  = "application/json; charset=utf-8"
}

try {
    $response = Invoke-RestMethod `
        -Uri "$url/api/products" `
        -Method Put `
        -Headers $headers `
        -Body $body

    Write-Host ""
    Write-Host "  Products pushed! ($($response.products) products)" -ForegroundColor Green
    Write-Host "  Discord embed will update within ~10 seconds." -ForegroundColor DarkGray
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "  Push failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
