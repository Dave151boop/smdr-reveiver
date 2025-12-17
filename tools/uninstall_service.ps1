<#
Uninstall the SMDR service installed with NSSM or sc
Usage: .\uninstall_service.ps1 -ServiceName SMDR
#>
param(
    [string]$ServiceName = "SMDR"
)

$nssm = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'nssm\nssm.exe'

if (Test-Path $nssm) {
    Write-Host "Stopping and removing service using NSSM"
    & $nssm stop $ServiceName 2>$null
    & $nssm remove $ServiceName confirm
} else {
    Write-Host "NSSM not found; falling back to sc.exe"
    sc.exe stop $ServiceName 2>$null
    sc.exe delete $ServiceName 2>$null
}
Write-Host "Uninstall completed."