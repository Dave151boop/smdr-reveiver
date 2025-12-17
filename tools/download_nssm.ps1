<#
Download NSSM (Non-Sucking Service Manager) and extract nssm.exe to tools\nssm\
Usage: .\download_nssm.ps1 [-Url <download_url>] [-OutDir <path>]
By default it downloads a known release and extracts the x64 binary.
#>
param(
    [string]$Url = "https://nssm.cc/release/nssm-2.24.zip",
    [string]$OutDir = "$(Split-Path -Parent $MyInvocation.MyCommand.Path)\nssm"
)

Write-Host "Downloading NSSM from $Url ..."
$zip = Join-Path $env:TEMP "nssm-download.zip"
Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing

Write-Host "Extracting to $OutDir ..."
if (-Not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $OutDir)

# Common NSSM builds keep the binary under a folder like nssm-2.24\win64\nssm.exe
# Attempt to copy the x64 build into the expected location
$exeSrc = Get-ChildItem -Path $OutDir -Filter nssm.exe -Recurse | Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1
if (-not $exeSrc) {
    $exeSrc = Get-ChildItem -Path $OutDir -Filter nssm.exe -Recurse | Select-Object -First 1
}
if ($exeSrc) {
    Copy-Item -Path $exeSrc.FullName -Destination (Join-Path $OutDir "nssm.exe") -Force
    Write-Host "nssm.exe placed in: " (Join-Path $OutDir "nssm.exe")
} else {
    Write-Host "Could not find nssm.exe inside the archive. Please extract manually and place nssm.exe into $OutDir"
}

Remove-Item $zip -Force
Write-Host "Done."