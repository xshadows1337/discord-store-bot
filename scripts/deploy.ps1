Set-Location "c:\Users\xshad\Desktop\Discord - Store Bot"
Write-Host "=== Deploying to Railway ==="
$out = railway up --detach 2>&1
Write-Host "Deploy output:"
$out | ForEach-Object { Write-Host $_ }
Write-Host "=== Deploy command finished ==="
Start-Sleep -Seconds 90
Write-Host "=== Checking logs ==="
$logs = railway logs 2>&1
$lastLines = ($logs | Select-Object -Last 15)
$lastLines | ForEach-Object { Write-Host $_ }
Write-Host "=== Done ==="
