<#
Install SMDR as a Windows service using NSSM (if available).
Usage: .\install_service.ps1 -InstallPath "C:\Program Files\SMDR" -ServiceName "SMDR"
If NSSM is not found in tools\nssm\nssm.exe, the script will attempt to use sc.exe as a fallback (works but is less graceful).
#>
param(
    [string]$InstallPath = "C:\Program Files\SMDR",
    [string]$ServiceName = "SMDR"
)

$nssm = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'nssm\nssm.exe'
$exe = Join-Path $InstallPath 'SMDR.exe'

if (Test-Path $nssm) {
    Write-Host "Installing service using NSSM: $nssm"
    & $nssm install $ServiceName $exe
    & $nssm set $ServiceName DisplayName "SMDR Service"
    & $nssm set $ServiceName Start SERVICE_AUTO_START
    & $nssm start $ServiceName
} else {
    Write-Host "NSSM not found at $nssm; attempting to use sc.exe (service will not be gracefully stoppable by SCM if the exe isn't a real service)."
    $quoted = '"' + $exe + '"'
    sc.exe create $ServiceName binPath= $quoted start= auto
    sc.exe start $ServiceName
}
Write-Host "Install completed. Use 'sc query $ServiceName' to check service status."