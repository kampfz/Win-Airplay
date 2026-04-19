"""Main GUI window built with customtkinter."""

import asyncio
import threading
from tkinter import filedialog, simpledialog
from typing import Dict, List, Optional

import customtkinter as ctk

from services.airplay import PinRequired, stop_playback, stream_url
from services.discovery import scan_devices
from services.streamer import HLSStreamer


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Win-AirPlay")
        self.geometry("520x300")
        self.resizable(False, False)

        self._devices: List[Dict[str, str]] = []
        self._selected_video: Optional[str] = None
        self._streamer = HLSStreamer()
        self._playing = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._build_ui()
        self._start_bg_loop()
        self._schedule_scan()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 16, "pady": 8}

        # Device row
        device_frame = ctk.CTkFrame(self, fg_color="transparent")
        device_frame.pack(fill="x", **pad)

        ctk.CTkLabel(device_frame, text="Apple TV:", width=90, anchor="w").pack(side="left")

        self._device_var = ctk.StringVar(value="Scanning…")
        self._device_menu = ctk.CTkOptionMenu(
            device_frame,
            variable=self._device_var,
            values=["Scanning…"],
            width=280,
        )
        self._device_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(device_frame, text="Rescan", width=70, command=self._schedule_scan).pack(
            side="left"
        )

        # File row
        file_frame = ctk.CTkFrame(self, fg_color="transparent")
        file_frame.pack(fill="x", **pad)

        ctk.CTkLabel(file_frame, text="Video file:", width=90, anchor="w").pack(side="left")

        self._file_label = ctk.CTkLabel(
            file_frame, text="No file selected", anchor="w", width=280
        )
        self._file_label.pack(side="left", padx=(0, 8))

        ctk.CTkButton(file_frame, text="Browse", width=70, command=self._pick_file).pack(
            side="left"
        )

        # Controls
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", **pad)

        self._play_btn = ctk.CTkButton(
            ctrl_frame, text="▶  Play", width=120, command=self._on_play, state="disabled"
        )
        self._play_btn.pack(side="left", padx=(90, 12))

        self._stop_btn = ctk.CTkButton(
            ctrl_frame,
            text="■  Stop",
            width=120,
            fg_color="#c0392b",
            hover_color="#922b21",
            command=self._on_stop,
            state="disabled",
        )
        self._stop_btn.pack(side="left")

        # Status bar
        self._status_var = ctk.StringVar(value="Ready")
        status_bar = ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            anchor="w",
            height=28,
            fg_color=("gray85", "gray20"),
            corner_radius=6,
        )
        status_bar.pack(fill="x", padx=16, pady=(4, 12))

    # ------------------------------------------------------------------
    # Background asyncio loop
    # ------------------------------------------------------------------

    def _start_bg_loop(self):
        self._loop = asyncio.new_event_loop()
        t = threading.Thread(target=self._loop.run_forever, daemon=True)
        t.start()

    def _run_async(self, coro):
        """Submit a coroutine to the background loop and return a Future."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------
    # Device scanning
    # ------------------------------------------------------------------

    def _schedule_scan(self):
        self._set_status("Scanning for Apple TV devices…")
        self._device_menu.configure(values=["Scanning…"])
        self._device_var.set("Scanning…")
        self._run_async(self._scan())

    async def _scan(self):
        try:
            devices = await scan_devices()
            self.after(0, self._on_scan_done, devices)
        except Exception as exc:
            self.after(0, self._set_status, f"Scan error: {exc}")

    def _on_scan_done(self, devices: List[Dict[str, str]]):
        self._devices = devices
        if devices:
            names = [d["name"] for d in devices]
            self._device_menu.configure(values=names)
            self._device_var.set(names[0])
            self._set_status(f"Found {len(devices)} device(s).")
        else:
            self._device_menu.configure(values=["No devices found"])
            self._device_var.set("No devices found")
            self._set_status("No Apple TV found. Is it on the same network?")
        self._refresh_play_state()

    # ------------------------------------------------------------------
    # File picker
    # ------------------------------------------------------------------

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.m4v *.wmv *.flv"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._selected_video = path
            short = path if len(path) <= 45 else "…" + path[-44:]
            self._file_label.configure(text=short)
            self._refresh_play_state()

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------

    def _refresh_play_state(self):
        ready = (
            self._selected_video
            and self._devices
            and self._device_var.get() not in ("Scanning…", "No devices found")
        )
        self._play_btn.configure(state="normal" if ready and not self._playing else "disabled")
        self._stop_btn.configure(state="normal" if self._playing else "disabled")

    def _on_play(self):
        device = self._selected_device()
        if device is None:
            return

        self._playing = True
        self._refresh_play_state()
        self._set_status("Starting transcoder…")

        self._run_async(self._play_pipeline(device, self._selected_video))

    async def _play_pipeline(self, device: Dict[str, str], video_path: str):
        try:
            self.after(0, self._set_status, "Transcoding & starting HTTP server…")
            url = await self._streamer.start(video_path)

            self.after(0, self._set_status, f"Connecting to {device['name']}…")

            def pin_provider() -> str:
                # Ask for PIN on the main thread; blocks the bg loop briefly but safe here.
                return simpledialog.askstring(
                    "Pairing PIN",
                    f"Enter the PIN shown on {device['name']}:",
                    parent=self,
                )

            try:
                await stream_url(device["identifier"], url, pin_provider=pin_provider)
            except PinRequired:
                self.after(0, self._set_status, "Pairing required — retry after PIN entry.")
                await self._streamer.stop()
                self.after(0, self._reset_playing)
                return

            self.after(0, self._set_status, f"Streaming to {device['name']}…")
        except Exception as exc:
            await self._streamer.stop()
            self.after(0, self._set_status, f"Error: {exc}")
            self.after(0, self._reset_playing)

    def _on_stop(self):
        self._set_status("Stopping playback…")
        device = self._selected_device()
        self._run_async(self._stop_pipeline(device))

    async def _stop_pipeline(self, device: Optional[Dict[str, str]]):
        try:
            await self._streamer.stop()
            if device:
                await stop_playback(device["identifier"])
        except Exception as exc:
            self.after(0, self._set_status, f"Stop error: {exc}")
        finally:
            self.after(0, self._reset_playing)
            self.after(0, self._set_status, "Stopped.")

    def _reset_playing(self):
        self._playing = False
        self._refresh_play_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _selected_device(self) -> Optional[Dict[str, str]]:
        name = self._device_var.get()
        for d in self._devices:
            if d["name"] == name:
                return d
        return None

    def _set_status(self, msg: str):
        self._status_var.set(msg)
