"""Main GUI window built with customtkinter."""

import asyncio
import threading
from tkinter import filedialog, simpledialog
from typing import Dict, List, Optional

import customtkinter as ctk

from pyatv.const import DeviceState

from services.airplay import AirPlaySession, PinRequired
from services.discovery import scan_devices
from services.streamer import HLSStreamer


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Win-AirPlay")
        self.geometry("520x370")
        self.resizable(False, False)

        self._devices: List[Dict[str, str]] = []
        self._selected_video: Optional[str] = None
        self._streamer = HLSStreamer()
        self._session: Optional[AirPlaySession] = None
        self._playing = False
        self._paused = False
        self._seeking = False
        self._updating_slider = False
        self._duration = 0
        self._poll_task = None
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

        # Transport controls: Play | Pause | Stop
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", **pad)

        # Left-pad to visually center the three 110px buttons inside the 488px inner width
        self._play_btn = ctk.CTkButton(
            ctrl_frame, text="▶  Play", width=110, command=self._on_play, state="disabled"
        )
        self._play_btn.pack(side="left", padx=(71, 8))

        self._pause_btn = ctk.CTkButton(
            ctrl_frame,
            text="⏸  Pause",
            width=110,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_pause_resume,
            state="disabled",
        )
        self._pause_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ctrl_frame,
            text="■  Stop",
            width=110,
            fg_color="#c0392b",
            hover_color="#922b21",
            command=self._on_stop,
            state="disabled",
        )
        self._stop_btn.pack(side="left")

        # Seek bar row
        seek_frame = ctk.CTkFrame(self, fg_color="transparent")
        seek_frame.pack(fill="x", padx=16, pady=(0, 8))

        self._seek_bar = ctk.CTkSlider(
            seek_frame, from_=0, to=1, width=370, command=self._on_seek_drag, state="disabled"
        )
        self._seek_bar.set(0)
        self._seek_bar.pack(side="left", padx=(0, 8))
        self._seek_bar.bind("<ButtonPress-1>", lambda _e: self._on_seek_press())
        self._seek_bar.bind("<ButtonRelease-1>", lambda _e: self._on_seek_release())

        self._time_label = ctk.CTkLabel(seek_frame, text="0:00 / 0:00", width=100, anchor="e")
        self._time_label.pack(side="left")

        # Status bar
        self._status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            anchor="w",
            height=28,
            fg_color=("gray85", "gray20"),
            corner_radius=6,
        ).pack(fill="x", padx=16, pady=(4, 12))

    # ------------------------------------------------------------------
    # Background asyncio loop
    # ------------------------------------------------------------------

    def _start_bg_loop(self):
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    def _run_async(self, coro):
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
    # Transport controls
    # ------------------------------------------------------------------

    def _refresh_play_state(self):
        ready = (
            self._selected_video
            and self._devices
            and self._device_var.get() not in ("Scanning…", "No devices found")
        )
        self._play_btn.configure(state="normal" if ready and not self._playing else "disabled")
        self._pause_btn.configure(state="normal" if self._playing else "disabled")
        self._stop_btn.configure(state="normal" if self._playing else "disabled")
        self._seek_bar.configure(state="normal" if self._playing else "disabled")

    def _on_play(self):
        device = self._selected_device()
        if device is None:
            return
        self._playing = True
        self._paused = False
        self._refresh_play_state()
        self._set_status("Starting transcoder…")
        self._run_async(self._play_pipeline(device, self._selected_video))

    async def _play_pipeline(self, device: Dict[str, str], video_path: str):
        try:
            self.after(0, self._set_status, "Transcoding & starting HTTP server…")
            url = await self._streamer.start(video_path)

            self.after(0, self._set_status, f"Connecting to {device['name']}…")

            self._session = AirPlaySession()

            def pin_provider() -> str:
                return simpledialog.askstring(
                    "Pairing PIN",
                    f"Enter the PIN shown on {device['name']}:",
                    parent=self,
                )

            try:
                await self._session.connect(device["identifier"], pin_provider=pin_provider)
            except PinRequired:
                self.after(0, self._set_status, "Pairing required — retry after PIN entry.")
                await self._streamer.stop()
                self._session = None
                self.after(0, self._reset_playing)
                return

            await self._session.stream(url)
            self.after(0, self._set_status, f"Streaming to {device['name']}…")

            self._session.start_push_updates(
                lambda ds, pos, dur: self.after(0, self._on_device_state, ds, pos, dur)
            )
            self._poll_task = asyncio.ensure_future(self._poll_position())

        except Exception as exc:
            await self._streamer.stop()
            if self._session:
                self._session.close()
                self._session = None
            self.after(0, self._set_status, f"Error: {exc}")
            self.after(0, self._reset_playing)

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    def _on_pause_resume(self):
        if self._paused:
            self._run_async(self._do_resume())
        else:
            self._run_async(self._do_pause())

    async def _do_pause(self):
        try:
            await self._session.pause()
            self.after(0, self._set_paused_ui, True)
        except Exception as exc:
            self.after(0, self._set_status, f"Pause error: {exc}")

    async def _do_resume(self):
        try:
            await self._session.resume()
            self.after(0, self._set_paused_ui, False)
        except Exception as exc:
            self.after(0, self._set_status, f"Resume error: {exc}")

    def _set_paused_ui(self, paused: bool):
        self._paused = paused
        self._pause_btn.configure(text="▶  Resume" if paused else "⏸  Pause")

    def _on_device_state(self, state: DeviceState, pos: int, dur: int) -> None:
        """Handle push updates from the Apple TV (remote control, Siri, etc.)."""
        if state == DeviceState.Paused and not self._paused:
            self._set_paused_ui(True)
        elif state == DeviceState.Playing and self._paused:
            self._set_paused_ui(False)
        elif state in (DeviceState.Stopped, DeviceState.Idle) and self._playing:
            self._on_stop()
            return
        self._update_seek_bar(pos, dur)

    # ------------------------------------------------------------------
    # Seek bar
    # ------------------------------------------------------------------

    def _on_seek_press(self):
        self._seeking = True

    def _on_seek_release(self):
        if not self._playing or self._duration == 0:
            self._seeking = False
            return
        pos = int(self._seek_bar.get() * self._duration)
        self._run_async(self._do_seek(pos))

    async def _do_seek(self, position: int):
        try:
            await self._session.seek(position)
        except Exception as exc:
            self.after(0, self._set_status, f"Seek error: {exc}")
        finally:
            self._seeking = False

    def _on_seek_drag(self, value: float):
        # Update the time label while dragging without seeking yet
        if self._updating_slider or self._duration == 0:
            return
        pos = int(value * self._duration)
        self._time_label.configure(text=f"{_fmt_time(pos)} / {_fmt_time(self._duration)}")

    def _update_seek_bar(self, pos: int, dur: int):
        if self._seeking:
            return
        self._duration = dur
        self._updating_slider = True
        if dur > 0:
            self._seek_bar.set(pos / dur)
        self._time_label.configure(text=f"{_fmt_time(pos)} / {_fmt_time(dur)}")
        self._updating_slider = False

    # ------------------------------------------------------------------
    # Position polling
    # ------------------------------------------------------------------

    async def _poll_position(self):
        while self._playing:
            if not self._seeking and self._session:
                try:
                    pos, dur = await self._session.position()
                    self.after(0, self._update_seek_bar, pos, dur)
                except Exception:
                    pass
            await asyncio.sleep(1.0)

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def _on_stop(self):
        self._set_status("Stopping playback…")
        self._run_async(self._stop_pipeline())

    async def _stop_pipeline(self):
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        try:
            await self._streamer.stop()
            if self._session:
                await self._session.stop()
                self._session = None
        except Exception as exc:
            self.after(0, self._set_status, f"Stop error: {exc}")
        finally:
            self.after(0, self._reset_playing)
            self.after(0, self._set_status, "Stopped.")

    def _reset_playing(self):
        self._playing = False
        self._paused = False
        self._duration = 0
        self._pause_btn.configure(text="⏸  Pause")
        self._seek_bar.set(0)
        self._time_label.configure(text="0:00 / 0:00")
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
