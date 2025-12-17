"""Small helper: convert a PNG to a multi-size Windows .ico using Pillow.

Usage: python tools/convert_icon.py resources/icon.png resources/icon.ico
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except Exception as e:
    print("Pillow is required to run this helper. Install with: python -m pip install Pillow")
    raise

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tools/convert_icon.py <input.png> <output.ico>")
        sys.exit(1)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    if not inp.exists():
        print(f"Input not found: {inp}")
        sys.exit(1)
    img = Image.open(inp)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(out, format="ICO", sizes=sizes)
    print(f"Wrote: {out}")
