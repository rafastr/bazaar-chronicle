# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path.cwd()
tesseract_dir = project_root / "third_party" / "tesseract"

hiddenimports = collect_submodules("web.routes")

datas = [
    ("web/templates", "web/templates"),
    ("web/static", "web/static"),
    ("resources", "resources"),
]

binaries = []

# Bundle local Tesseract if present
if tesseract_dir.exists():
    exe_path = tesseract_dir / "tesseract.exe"
    if exe_path.exists():
        binaries.append((str(exe_path), "tesseract"))

    for dll in tesseract_dir.glob("*.dll"):
        binaries.append((str(dll), "tesseract"))

    tessdata_dir = tesseract_dir / "tessdata"
    if tessdata_dir.exists():
        for traineddata in tessdata_dir.glob("*"):
            datas.append((str(traineddata), "tesseract/tessdata"))

a = Analysis(
    ["bazaar_chronicle.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "matplotlib",
        "pandas",
        "scipy",
        "IPython",
        "jupyter",
        "cv2.qt",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BazaarChronicle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    version="version.txt",
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BazaarChronicle",
)
