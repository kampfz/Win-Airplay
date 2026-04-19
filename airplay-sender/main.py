"""Entry point — ensures ffmpeg is present, then launches the Win-AirPlay GUI."""

import os
import sys
import tkinter as tk
from tkinter import ttk

# Ensure the project root is on the path when run as a script or bundled exe.
sys.path.insert(0, os.path.dirname(__file__))


def _ensure_ffmpeg_with_ui():
    """Download ffmpeg if missing, showing a small progress dialog."""
    from scripts.get_ffmpeg import ensure_ffmpeg

    # Skip download check inside a PyInstaller bundle — ffmpeg is already embedded.
    if hasattr(sys, "_MEIPASS"):
        return

    dest = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
    if os.path.isfile(dest):
        return

    # Build a minimal progress window before customtkinter is imported.
    root = tk.Tk()
    root.title("Win-AirPlay — First-run setup")
    root.geometry("380x110")
    root.resizable(False, False)
    root.eval("tk::PlaceWindow . center")

    tk.Label(root, text="Downloading ffmpeg (one-time setup)…", pady=12).pack()

    bar = ttk.Progressbar(root, length=320, mode="determinate", maximum=100)
    bar.pack()

    pct_var = tk.StringVar(value="0%")
    tk.Label(root, textvariable=pct_var, pady=6).pack()

    def on_progress(pct: int):
        bar["value"] = pct
        pct_var.set(f"{pct}%")
        root.update_idletasks()

    root.update()

    try:
        ensure_ffmpeg(progress_cb=on_progress)
    finally:
        root.destroy()


def main():
    _ensure_ffmpeg_with_ui()

    from gui.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
