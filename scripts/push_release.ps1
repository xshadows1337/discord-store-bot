<#
.SYNOPSIS
    Push a release to your Railway server for the Steam Hub installer.

.DESCRIPTION
    This script uploads a release zip file and creates the release entry
    so the installer can see and download it.

.EXAMPLE
    # Push a release with a zip file:
    .\push_release.ps1 -Tag "v2.35.0" -ZipFile "C:\path\to\millennium-v2.35.0-windows-x86_64.zip"
    
    # Push with install size file too:
    .\push_release.ps1 -Tag "v2.35.0" -ZipFile "C:\path\to\millennium-v2.35.0-windows-x86_64.zip" -InstallSizeFile "C:\path\to\millennium-v2.35.0-windows-x86_64.installsize"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Tag,

    [Parameter(Mandatory=$true)]
    [string]$ZipFile,

    [string]$InstallSizeFile = "",

    [switch]$Prerelease,

    [string]$ServerUrl = "https://empowering-exploration-production.up.railway.app",

    [string]$Secret = "Hacker11!@._"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ZipFile)) {
    Write-Host "ERROR: Zip file not found: $ZipFile" -ForegroundColor Red
    exit 1
}

$zipFileName = [System.IO.Path]::GetFileName($ZipFile)
$zipFileSize = (Get-Item $ZipFile).Length

Write-Host "=== Pushing Release $Tag ===" -ForegroundColor Cyan
Write-Host "  Zip: $zipFileName ($([math]::Round($zipFileSize / 1MB, 2)) MB)"

# Step 1: Upload the zip file
Write-Host "`n[1/3] Uploading zip file..." -ForegroundColor Yellow
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"

$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"filename`"$LF",
    $zipFileName,
    "--$boundary",
    "Content-Disposition: form-data; name=`"file`"; filename=`"$zipFileName`"",
    "Content-Type: application/octet-stream$LF",
    ""
)
$bodyStart = [System.Text.Encoding]::UTF8.GetBytes(($bodyLines -join $LF))
$bodyEnd = [System.Text.Encoding]::UTF8.GetBytes("$LF--$boundary--$LF")
$fileBytes = [System.IO.File]::ReadAllBytes($ZipFile)

$ms = New-Object System.IO.MemoryStream
$ms.Write($bodyStart, 0, $bodyStart.Length)
$ms.Write($fileBytes, 0, $fileBytes.Length)
$ms.Write($bodyEnd, 0, $bodyEnd.Length)
$fullBody = $ms.ToArray()
$ms.Dispose()

$uploadResp = Invoke-RestMethod -Uri "$ServerUrl/api/releases/upload-asset" `
    -Method Post `
    -Headers @{ "X-Releases-Secret" = $Secret } `
    -ContentType "multipart/form-data; boundary=$boundary" `
    -Body $fullBody `
    -TimeoutSec 300

Write-Host "  Uploaded: $($uploadResp.filename) -> $($uploadResp.browser_download_url)" -ForegroundColor Green
$downloadUrl = $uploadResp.browser_download_url

# Step 2: Upload installsize file if provided
$installSizeUrl = ""
if ($InstallSizeFile -and (Test-Path $InstallSizeFile)) {
    $isFileName = [System.IO.Path]::GetFileName($InstallSizeFile)
    Write-Host "`n[2/3] Uploading installsize file..." -ForegroundColor Yellow
    
    $boundary2 = [System.Guid]::NewGuid().ToString()
    $bodyLines2 = @(
        "--$boundary2",
        "Content-Disposition: form-data; name=`"filename`"$LF",
        $isFileName,
        "--$boundary2",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$isFileName`"",
        "Content-Type: text/plain$LF",
        ""
    )
    $bodyStart2 = [System.Text.Encoding]::UTF8.GetBytes(($bodyLines2 -join $LF))
    $bodyEnd2 = [System.Text.Encoding]::UTF8.GetBytes("$LF--$boundary2--$LF")
    $isBytes = [System.IO.File]::ReadAllBytes($InstallSizeFile)
    
    $ms2 = New-Object System.IO.MemoryStream
    $ms2.Write($bodyStart2, 0, $bodyStart2.Length)
    $ms2.Write($isBytes, 0, $isBytes.Length)
    $ms2.Write($bodyEnd2, 0, $bodyEnd2.Length)
    $fullBody2 = $ms2.ToArray()
    $ms2.Dispose()
    
    $isResp = Invoke-RestMethod -Uri "$ServerUrl/api/releases/upload-asset" `
        -Method Post `
        -Headers @{ "X-Releases-Secret" = $Secret } `
        -ContentType "multipart/form-data; boundary=$boundary2" `
        -Body $fullBody2 `
        -TimeoutSec 60
    
    $installSizeUrl = $isResp.browser_download_url
    Write-Host "  Uploaded: $($isResp.filename)" -ForegroundColor Green
} else {
    Write-Host "`n[2/3] No installsize file, skipping..." -ForegroundColor DarkGray
}

# Step 3: Compute SHA256 digest of the zip
$hash = (Get-FileHash -Path $ZipFile -Algorithm SHA256).Hash.ToLower()
Write-Host "`n  SHA256: $hash"

# Step 4: Push the release JSON
Write-Host "`n[3/3] Pushing release metadata..." -ForegroundColor Yellow

$assets = @(
    @{
        name = $zipFileName
        size = $zipFileSize
        browser_download_url = $downloadUrl
        content_type = "application/zip"
        state = "uploaded"
        digest = "sha256:$hash"
    }
)

if ($installSizeUrl) {
    $isName = [System.IO.Path]::GetFileName($InstallSizeFile)
    $assets += @{
        name = $isName
        size = (Get-Item $InstallSizeFile).Length
        browser_download_url = $installSizeUrl
        content_type = "text/plain"
        state = "uploaded"
        digest = ""
    }
}

$releaseBody = @{
    tag_name = $Tag
    name = $Tag
    prerelease = [bool]$Prerelease
    draft = $false
    published_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    assets = $assets
    body = "Release $Tag pushed via push_release.ps1"
} | ConvertTo-Json -Depth 5

$pushResp = Invoke-RestMethod -Uri "$ServerUrl/api/releases/push" `
    -Method Post `
    -Headers @{ "X-Releases-Secret" = $Secret; "Content-Type" = "application/json" } `
    -Body $releaseBody `
    -TimeoutSec 30

Write-Host "`n=== Release $Tag pushed successfully! ===" -ForegroundColor Green
Write-Host "  Total releases on server: $($pushResp.total)"
Write-Host "`nThe installer will now show this version." -ForegroundColor Cyan
