Param(
    [string]$Python = "python"
)

# Build a portable single-file Windows executable (SMDR.exe) using PyInstaller
Set-StrictMode -Version Latest

Write-Host "Installing build requirements..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install -r dev-requirements.txt

# Clean prior builds
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path *.spec) { Remove-Item -Force *.spec }

# Prepare optional arguments
$iconArg = ""
$iconPngPath = Join-Path -Path (Get-Location) -ChildPath "resources\icon.png"
$iconPath = Join-Path -Path (Get-Location) -ChildPath "resources\icon.ico"
# If user provided a PNG but not an ICO, try to convert it using Pillow
if (Test-Path $iconPngPath -and -not (Test-Path $iconPath)) {
    Write-Warning "Found PNG icon at $iconPngPath but no .ico — Pillow conversion is skipped in this environment. To include an icon, install Pillow and re-run the script or provide resources\icon.ico yourself."
}
if (Test-Path $iconPath) {
    Write-Host "Using icon: $iconPath"
    $iconArg = '--icon "' + $iconPath + '"'
}

# Attempt to find PySide6 plugins (helps with platform and tray plugins)
$pluginsArg = ""
$pyCmd = "import importlib, os, PySide6, sys; p = os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'plugins'); print(p if os.path.isdir(p) else '')"
$pluginsPath = & $Python -c $pyCmd
if ($pluginsPath -and (Test-Path $pluginsPath)) {
    Write-Host "Found PySide6 plugins at: $pluginsPath"
    # add plugins as data so PyInstaller includes them
    $pluginsArg = '--add-data "' + $pluginsPath + ';PySide6/Qt/plugins"'
}

# Extra data: include the smdr package and the top-level resources directory
# This ensures files like resources/icon.png are packaged and available at runtime.
$addData = '--add-data "smdr;smdr"'
$resourcesPath = Join-Path -Path (Get-Location) -ChildPath "resources"
if (Test-Path $resourcesPath) {
    Write-Host "Including resources directory: $resourcesPath"
    $addData = $addData + ' --add-data "' + $resourcesPath + ';resources"'
} else {
    Write-Host "No top-level resources directory found at $resourcesPath; skipping." 
}

# Build: single file (--onefile) is convenient; note it extracts to a temp dir at runtime
$cmdArgs = "--clean --noconfirm --onefile --windowed --name SMDR $addData $pluginsArg $iconArg main.py"
Write-Host "Running PyInstaller via: $Python -m PyInstaller $cmdArgs"
# Use Invoke-Expression to allow proper argument parsing (avoids relying on Scripts on PATH)
$fullCmd = "$Python -m PyInstaller $cmdArgs"
Invoke-Expression $fullCmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Build complete. Artifact file: dist\SMDR.exe"
Write-Host "Note: --onefile builds create a single executable that extracts itself at runtime to a temporary folder. If you prefer a folder distribution, use --onedir instead."
