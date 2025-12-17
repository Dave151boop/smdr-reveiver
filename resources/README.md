Place your program icon here as `icon.png` (the image you attached is suitable).

The build helper (`tools/build_windows.ps1`) will automatically try to convert `icon.png` to `icon.ico` using Pillow when building; otherwise you can convert it yourself with:

    python tools/convert_icon.py resources/icon.png resources/icon.ico

If you prefer, place `icon.ico` directly in `resources/` and the build will pick it up automatically.