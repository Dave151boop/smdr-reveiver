SMDR Receiver App

This small app listens for SMDR data (Avaya IP Office style) on TCP (default port 7000), displays incoming messages in a simple GUI and appends them to a log file. It minimizes to the system tray and has a File menu with Save, Change Port, and Exit.

Quick start

1. Create a virtualenv and activate it (recommended):
   python -m venv .venv
   .venv\Scripts\activate   (Windows)

2. Install dependencies:
   pip install -r requirements.txt

3. Run the app:
   python main.py

Features

- Listens on a configurable TCP port (default 7000)
- Displays incoming SMDR lines in a text window
- Appends all incoming data to a log file (`smdr.log` by default)
- File menu: Save As, Change Port, Exit
- Minimizes to system tray

Test helper

A small test sender script is provided to send test SMDR lines to the port.

Build a portable Windows distribution

You can create a standalone, portable exe (no Python required) using PyInstaller.

1. Install dev requirements:

    python -m pip install -r dev-requirements.txt

2. Add a program icon (optional):

   - Place your icon source PNG at `resources/icon.png` (the attached image is perfect). The build script will automatically try to convert it to `resources/icon.ico` using Pillow.
   - Or place `resources/icon.ico` directly (preferred if you already have an .ico).

3. Run the build helper (PowerShell):

    .\tools\build_windows.ps1

This produces a single-file executable `dist\SMDR.exe` by default (PyInstaller `--onefile`). The executable is fully portable, but note that `--onefile` extracts itself into a temporary directory at runtime (this is normal). The app writes `smdr.log` next to the executable when run from the bundled distribution (or to the location set by the `SMDR_LOG_FILE` env var).

When run from a bundled executable, the app will prefer `resources/icon.ico` (or `resources/icon.png`) as the application/tray icon if present. The build helper will attempt to convert `resources/icon.png` to `resources/icon.ico` automatically.

If you prefer a folder distribution (no extraction at runtime), change `--onefile` to `--onedir` in `tools/build_windows.ps1` or CI.

Automated release builds (signed executable)

A GitHub Actions workflow has been added to build and optionally sign the Windows executable when a GitHub release is published: `.github/workflows/release-windows.yml`.

To enable signing you need to add two repository secrets:
- `CERT_PFX` — base64-encoded contents of a code signing certificate in `.pfx` format
- `CERT_PASSWORD` — the password for the `.pfx` file

Notes:
- The workflow will upload an unsigned artifact named `SMDR-<tag>-unsigned.exe` and then (if signing is configured) sign `dist/SMDR.exe` and upload the signed `SMDR-<tag>.exe`.
- On Windows runners the workflow attempts to use `signtool` if available, falling back to `osslsigncode` if present.
- To create the base64 PFX: `base64 -w0 cert.pfx | pbcopy` (macOS/Linux) or use `certutil -encode cert.pfx cert.b64` and copy the content into the `CERT_PFX` secret in the repo settings.


Optionally, CI is set up to produce a Windows build as part of the repository on pushes to `main` (see `.github/workflows/build-windows.yml`).

Running tests

- Install test requirement: `pip install -r requirements.txt` (this includes `pytest`)
- Run the test suite (targeting the package tests directory):

    python -m pytest -q tests

The test suite includes a small integration test that starts the `SMDRServer` on an ephemeral port and verifies that incoming data is delivered to the `on_data` callback.
