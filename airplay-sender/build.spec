# PyInstaller spec file for Win-AirPlay
# Build with: pyinstaller build.spec

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        # Bundle ffmpeg.exe if placed next to main.py
        # ("ffmpeg.exe", "."),
    ],
    datas=[
        # customtkinter ships its own theme assets
        (
            "../../Lib/site-packages/customtkinter",
            "customtkinter",
        ),
    ],
    hiddenimports=[
        "zeroconf",
        "zeroconf._utils.ipaddress",
        "zeroconf._dns",
        "aiohttp",
        "pyatv",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="WinAirPlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # no console window
    icon=None,      # set to "icon.ico" if you add one
)
