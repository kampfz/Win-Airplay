"""Entry point — ensures ffmpeg is present, handles single-instance IPC, then launches the GUI."""

import os
import socket
import sys
import threading
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(__file__))

# All instances share this port for single-instance handoff.
_IPC_PORT = 57321


def _ensure_ffmpeg_with_ui():
    from scripts.get_ffmpeg import ensure_ffmpeg

    if hasattr(sys, "_MEIPASS"):
        return

    dest = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
    if os.path.isfile(dest):
        return

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


def _try_handoff(filepath: str) -> bool:
    """Send *filepath* to an already-running instance. Returns True on success."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", _IPC_PORT))
            s.sendall(filepath.encode("utf-8"))
        return True
    except OSError:
        return False


def _start_ipc_listener(callback):
    """Accept file-path messages from future launches and forward to *callback*."""
    def serve():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.bind(("127.0.0.1", _IPC_PORT))
            except OSError:
                return  # another instance is already listening
            srv.listen(5)
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                with conn:
                    data = conn.recv(4096)
                    if data:
                        callback(data.decode("utf-8", errors="replace"))

    threading.Thread(target=serve, daemon=True).start()


def main():
    _ensure_ffmpeg_with_ui()

    initial_file = sys.argv[1] if len(sys.argv) > 1 else None

    # If the app is already running in the tray, hand off the file and exit.
    if initial_file and _try_handoff(initial_file):
        return

    from gui.app import App
    app = App(initial_file=initial_file)
    _start_ipc_listener(lambda path: app.after(0, app.open_file, path))
    app.mainloop()


if __name__ == "__main__":
    main()
