"""
Add or remove a Windows Explorer right-click context menu entry that sends
a video file directly to Win-AirPlay.

Usage
-----
Install (point to the built exe):
    python scripts/register_context_menu.py install dist\\WinAirPlay.exe

Install (auto-locate dist\\WinAirPlay.exe relative to this script):
    python scripts/register_context_menu.py install

Uninstall:
    python scripts/register_context_menu.py uninstall

Registry keys are written to HKCU so no administrator rights are required.
Changes take effect immediately in new Explorer windows; you may need to
restart an already-open Explorer window to see them.
"""

import os
import sys

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".m4v", ".wmv", ".flv", ".ts", ".m2ts"]
_MENU_KEY = "AirPlayToAppleTV"
_MENU_LABEL = "AirPlay to Apple TV"


def install(exe_path: str) -> None:
    import winreg

    exe_path = os.path.abspath(exe_path)
    if not os.path.isfile(exe_path):
        print(f"Error: executable not found: {exe_path}")
        print("Build the app first with:  pyinstaller airplay-sender/build.spec")
        sys.exit(1)

    cmd = f'"{exe_path}" "%1"'
    icon = f'"{exe_path}",0'

    for ext in VIDEO_EXTENSIONS:
        shell_path = f"Software\\Classes\\{ext}\\shell\\{_MENU_KEY}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell_path) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _MENU_LABEL)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell_path + "\\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)

    print(f"Registered '{_MENU_LABEL}' for {len(VIDEO_EXTENSIONS)} extension(s).")
    print(f"  Executable : {exe_path}")


def uninstall() -> None:
    import winreg

    removed = 0
    for ext in VIDEO_EXTENSIONS:
        base = f"Software\\Classes\\{ext}\\shell\\{_MENU_KEY}"
        for subkey in ("\\command", ""):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + subkey)
                removed += 1
            except FileNotFoundError:
                pass

    print(f"Unregistered '{_MENU_LABEL}' ({removed} registry key(s) removed).")


def _default_exe() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "dist", "WinAirPlay.exe")
    )


def main() -> None:
    if sys.platform != "win32":
        print("Context menu registration is only supported on Windows.")
        sys.exit(1)

    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "uninstall"):
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "install":
        install(sys.argv[2] if len(sys.argv) > 2 else _default_exe())
    else:
        uninstall()


if __name__ == "__main__":
    main()
