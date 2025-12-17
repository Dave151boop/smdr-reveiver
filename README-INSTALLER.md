SMDR Windows Installer & Service

This repository includes scripts to build an Inno Setup based installer that installs SMDR and registers it as a Windows Service.

Overview
- Installer: installer/SMDR.iss — an Inno Setup script that copies the built EXE and resources into Program Files and uses NSSM to register the service.
- NSSM: Non-Sucking Service Manager (https://nssm.cc/) is used to run the non-service EXE as a Windows service in a robust way.
- Helpers:
  - tools/download_nssm.ps1 — Downloads and extracts NSSM into tools/nssm/
  - tools/install_service.ps1 — Installs the SMDR service using NSSM (or sc.exe as a fallback)
  - tools/uninstall_service.ps1 — Uninstalls the service

How to build the installer (manual steps)
1. Build a PyInstaller EXE (from the repo root):
   python -m PyInstaller --clean --noconfirm --onefile --windowed --name SMDR --add-data "smdr;smdr" --add-data "resources\icon.png;resources\icon.png" --icon resources/icon.png main.py

2. Ensure `nssm.exe` is present at `tools\nssm\nssm.exe`. Use the helper:
   powershell -ExecutionPolicy Bypass -File tools\download_nssm.ps1

3. Compile the installer (requires Inno Setup 6):
   iscc installer\SMDR.iss

4. Run the produced installer (run as Administrator). It will copy files and register the SMDR service using NSSM.

Manual service management
- Install service (alternative to installer):
  powershell -ExecutionPolicy Bypass -File tools\install_service.ps1 -InstallPath "C:\Program Files\SMDR" -ServiceName SMDR

- Uninstall service:
  powershell -ExecutionPolicy Bypass -File tools\uninstall_service.ps1 -ServiceName SMDR

Notes & caveats
- The service is created with NSSM which runs any executable as a service and allows for easier start/stop behavior. If NSSM isn't available the helper falls back to sc.exe which can create a service for an arbitrary executable but won't manage graceful stop/start unless the executable handles service control.
- The installer requires Administrator privileges to register services.
- Optionally you can create a signed installer if you sign the produced EXE and the installer.
