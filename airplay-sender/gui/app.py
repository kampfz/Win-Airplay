"""Main GUI window built with customtkinter."""

import asyncio
import os
import threading
import tkinter as tk
from tkinter import filedialog, simpledialog
from typing import Dict, List, Optional

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw
from pyatv.const import DeviceState
from tkinterdnd2 import DND_FILES, TkinterDnD

from services.airplay import AirPlaySession, PinRequired
from services.discovery import scan_devices
from services.playlist import Playlist
from services.streamer import HLSStreamer


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_ACTIVE_BTN = {"fg_color": "#1a73e8", "hover_color": "#1558b0"}
_INACTIVE_BTN = {"fg_color": "gray35", "hover_color": "gray25"}


def _fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _make_tray_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(26, 115, 232, 255))
    draw.polygon([(20, 16), (20, 48), (52, 32)], fill=(255, 255, 255, 255))
    return img


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, initial_file: Optional[str] = None):
        super().__init__()
        self.title("Win-AirPlay")
        self.geometry("520x640")
        self.resizable(False, False)

        self._devices: List[Dict[str, str]] = []
        self._playlist = Playlist()
        self._current_device: Optional[Dict[str, str]] = None
        self._streamer = HLSStreamer()
        self._session: Optional[AirPlaySession] = None
        self._playing = False
        self._paused = False
        self._seeking = False
        self._updating_slider = False
        self._duration = 0
        self._poll_task = None
        self._mirror_mode = False
        self._drag_start: Optional[int] = None
        self._tray: Optional[pystray.Icon] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self.TkdndVersion = TkinterDnD._require(self)

        self._build_ui()
        self._start_bg_loop()
        self._setup_tray()
        self._schedule_scan()

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        if initial_file:
            self.after(100, self.open_file, initial_file)

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
            device_frame, variable=self._device_var, values=["Scanning…"], width=280,
        )
        self._device_menu.pack(side="left", padx=(0, 8))
        ctk.CTkButton(device_frame, text="Rescan", width=70, command=self._schedule_scan).pack(side="left")

        # Now playing row
        np_frame = ctk.CTkFrame(self, fg_color="transparent")
        np_frame.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(np_frame, text="Now playing:", width=90, anchor="w").pack(side="left")
        self._now_playing_label = ctk.CTkLabel(
            np_frame, text="—", anchor="w", width=400
        )
        self._now_playing_label.pack(side="left")

        # Mirror switch row
        mirror_frame = ctk.CTkFrame(self, fg_color="transparent")
        mirror_frame.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(mirror_frame, text="", width=90).pack(side="left")
        self._mirror_switch = ctk.CTkSwitch(
            mirror_frame,
            text="Mirror screen  (streams your desktop to Apple TV)",
            command=self._on_mirror_toggle,
            onvalue=True,
            offvalue=False,
        )
        self._mirror_switch.pack(side="left")

        # Transport controls
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", **pad)

        self._play_btn = ctk.CTkButton(
            ctrl_frame, text="▶  Play", width=110, command=self._on_play, state="disabled"
        )
        self._play_btn.pack(side="left", padx=(71, 8))

        self._pause_btn = ctk.CTkButton(
            ctrl_frame, text="⏸  Pause", width=110,
            fg_color="gray40", hover_color="gray30",
            command=self._on_pause_resume, state="disabled",
        )
        self._pause_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ctrl_frame, text="■  Stop", width=110,
            fg_color="#c0392b", hover_color="#922b21",
            command=self._on_stop, state="disabled",
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

        # ── Playlist panel ──────────────────────────────────────────────

        playlist_outer = ctk.CTkFrame(self, corner_radius=8)
        playlist_outer.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Header: title + action buttons
        hdr = ctk.CTkFrame(playlist_outer, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(hdr, text="Playlist", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        for text, cmd in [
            ("↓", self._on_playlist_down),
            ("↑", self._on_playlist_up),
            ("−", self._on_playlist_remove),
            ("＋", self._on_playlist_add),
        ]:
            ctk.CTkButton(hdr, text=text, width=34, command=cmd).pack(side="right", padx=2)

        # Listbox with scrollbar
        lb_frame = tk.Frame(playlist_outer, bg="#2b2b2b")
        lb_frame.pack(fill="both", expand=True, padx=8, pady=2)

        scrollbar = tk.Scrollbar(lb_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._playlist_lb = tk.Listbox(
            lb_frame,
            bg="#2b2b2b",
            fg="#e0e0e0",
            selectbackground="#1a73e8",
            selectforeground="white",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
        )
        self._playlist_lb.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._playlist_lb.yview)
        self._playlist_lb.bind("<<ListboxSelect>>", self._on_lb_select)
        self._playlist_lb.bind("<Double-Button-1>", self._on_lb_double_click)
        self._playlist_lb.bind("<Button-1>", self._on_lb_drag_start)
        self._playlist_lb.bind("<B1-Motion>", self._on_lb_drag_motion)
        self._playlist_lb.bind("<ButtonRelease-1>", self._on_lb_drag_release)
        self._playlist_lb.drop_target_register(DND_FILES)
        self._playlist_lb.dnd_bind("<<Drop>>", self._on_dnd_drop)

        # Shuffle / Loop toggles
        toggle_row = ctk.CTkFrame(playlist_outer, fg_color="transparent")
        toggle_row.pack(fill="x", padx=8, pady=(4, 8))

        self._shuffle_btn = ctk.CTkButton(
            toggle_row, text="⇄  Shuffle", width=110,
            command=self._on_shuffle_toggle, **_INACTIVE_BTN,
        )
        self._shuffle_btn.pack(side="left", padx=(0, 8))

        self._loop_btn = ctk.CTkButton(
            toggle_row, text="↺  Loop", width=110,
            command=self._on_loop_toggle, **_INACTIVE_BTN,
        )
        self._loop_btn.pack(side="left")

        # Status bar — read-only entry so the text is selectable/copyable
        self._status_var = ctk.StringVar(value="Ready")
        self._status_entry = ctk.CTkEntry(
            self, textvariable=self._status_var,
            height=28, fg_color=("gray85", "gray20"),
            border_width=0, corner_radius=6,
            state="readonly",
        )
        self._status_entry.pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._tray_show, default=True),
            pystray.MenuItem("Stop Playback", self._tray_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self._tray = pystray.Icon("Win-AirPlay", _make_tray_image(), "Win-AirPlay", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _hide_to_tray(self):
        self.withdraw()

    def _tray_show(self, _icon, _item):
        self.after(0, self.deiconify)

    def _tray_stop(self, _icon, _item):
        self.after(0, self._on_stop)

    def _tray_quit(self, _icon, _item):
        self._tray.stop()
        self.after(0, self.destroy)

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
    # Playlist management
    # ------------------------------------------------------------------

    def _on_playlist_add(self):
        paths = filedialog.askopenfilenames(
            title="Add files to playlist",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.m4v *.wmv *.flv"),
                ("All files", "*.*"),
            ],
        )
        for path in paths:
            self._playlist.add(path)
        self._update_playlist_display()
        self._refresh_play_state()

    def _on_dnd_drop(self, event):
        # tkinterdnd2 returns paths as a Tcl list string, e.g. {/path/to/file} or
        # multiple paths separated by spaces with braces around paths that have spaces.
        raw = event.data
        # Use Tk's splitlist to correctly handle spaces and braces.
        try:
            paths = self.tk.splitlist(raw)
        except Exception:
            paths = raw.split()

        video_exts = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".wmv", ".flv", ".ts", ".m2ts"}
        added = 0
        for path in paths:
            if os.path.isfile(path) and os.path.splitext(path)[1].lower() in video_exts:
                self._playlist.add(path)
                added += 1

        if added:
            self._update_playlist_display()
            self._update_now_playing()
            self._refresh_play_state()
            self._set_status(f"Added {added} file(s) to playlist.")

    def _on_playlist_remove(self):
        sel = self._playlist_lb.curselection()
        if not sel:
            return
        index = sel[0]
        self._playlist.remove(index)
        self._update_playlist_display()
        self._refresh_play_state()

    def _on_playlist_up(self):
        sel = self._playlist_lb.curselection()
        if not sel:
            return
        new_idx = self._playlist.move(sel[0], -1)
        self._update_playlist_display()
        self._playlist_lb.selection_set(new_idx)

    def _on_playlist_down(self):
        sel = self._playlist_lb.curselection()
        if not sel:
            return
        new_idx = self._playlist.move(sel[0], +1)
        self._update_playlist_display()
        self._playlist_lb.selection_set(new_idx)

    def _on_lb_select(self, _event):
        if self._drag_start is not None:
            return  # selection changes during drag are visual only
        sel = self._playlist_lb.curselection()
        if sel and not self._playing:
            self._playlist.select(sel[0])
            self._update_now_playing()

    def _on_lb_drag_start(self, event):
        idx = self._playlist_lb.nearest(event.y)
        if idx >= 0:
            self._drag_start = idx

    def _on_lb_drag_motion(self, event):
        if self._drag_start is None:
            return
        self._playlist_lb.configure(cursor="fleur")
        target = max(0, min(len(self._playlist) - 1, self._playlist_lb.nearest(event.y)))
        self._playlist_lb.selection_clear(0, tk.END)
        self._playlist_lb.selection_set(target)

    def _on_lb_drag_release(self, event):
        self._playlist_lb.configure(cursor="")
        if self._drag_start is None:
            return
        start = self._drag_start
        self._drag_start = None
        target = max(0, min(len(self._playlist) - 1, self._playlist_lb.nearest(event.y)))
        if target == start:
            return  # plain click — leave normal select in place
        self._playlist.move(start, target - start)
        self._update_playlist_display()
        self._playlist_lb.selection_set(target)
        self._refresh_play_state()

    def _on_lb_double_click(self, _event):
        sel = self._playlist_lb.curselection()
        if not sel:
            return
        index = sel[0]
        if self._playing:
            self._run_async(self._jump_to_track(index))
        else:
            self._playlist.select(index)
            self._update_now_playing()
            self._on_play()

    def _on_shuffle_toggle(self):
        self._playlist.shuffle = not self._playlist.shuffle
        self._shuffle_btn.configure(**(
            _ACTIVE_BTN if self._playlist.shuffle else _INACTIVE_BTN
        ))

    def _on_loop_toggle(self):
        self._playlist.loop = not self._playlist.loop
        self._loop_btn.configure(**(
            _ACTIVE_BTN if self._playlist.loop else _INACTIVE_BTN
        ))

    def _update_playlist_display(self):
        self._playlist_lb.delete(0, tk.END)
        current = self._playlist.current_index
        for i, path in enumerate(self._playlist.items):
            prefix = "▶ " if i == current else "   "
            self._playlist_lb.insert(tk.END, prefix + os.path.basename(path))
        if 0 <= current < len(self._playlist):
            self._playlist_lb.see(current)

    def _update_now_playing(self):
        name = self._playlist.display_name(self._playlist.current_index)
        self._now_playing_label.configure(text=name or "—")

    # ------------------------------------------------------------------
    # Mirror toggle
    # ------------------------------------------------------------------

    def _on_mirror_toggle(self):
        self._mirror_mode = self._mirror_switch.get()
        if self._mirror_mode:
            self._now_playing_label.configure(text="Desktop — screen capture")
        else:
            self._update_now_playing()
        self._refresh_play_state()

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    def _refresh_play_state(self):
        source_ready = self._mirror_mode or len(self._playlist) > 0
        device_ready = (
            bool(self._devices)
            and self._device_var.get() not in ("Scanning…", "No devices found")
        )
        ready = source_ready and device_ready
        self._play_btn.configure(state="normal" if ready and not self._playing else "disabled")
        self._pause_btn.configure(state="normal" if self._playing else "disabled")
        self._stop_btn.configure(state="normal" if self._playing else "disabled")
        self._seek_bar.configure(state="normal" if self._playing else "disabled")
        self._mirror_switch.configure(state="disabled" if self._playing else "normal")

    def _on_play(self):
        device = self._selected_device()
        if device is None:
            return
        if not self._mirror_mode:
            if not self._playlist.items:
                return
            if self._playlist.current_index < 0:
                self._playlist.select(0)
        self._current_device = device
        self._playing = True
        self._paused = False
        self._refresh_play_state()
        self._run_async(self._play_pipeline(device))

    async def _play_pipeline(self, device: Dict[str, str]):
        try:
            if self._mirror_mode:
                self.after(0, self._set_status, "Starting screen capture…")
                url = await self._streamer.start_mirror()
            else:
                path = self._playlist.current
                self.after(0, self._set_status, "Transcoding & starting HTTP server…")
                url = await self._streamer.start(path)

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

            if self._mirror_mode:
                self.after(0, self._set_status, "Mirroring screen…")
            else:
                name = os.path.basename(self._playlist.current)
                self.after(0, self._set_status, f"Playing: {name}")
                self.after(0, self._update_now_playing)
                self.after(0, self._update_playlist_display)

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
    # Playlist auto-advance
    # ------------------------------------------------------------------

    async def _advance_and_play(self):
        """Called when a track ends naturally — advance the playlist and stream next."""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        await self._streamer.stop()

        next_path = self._playlist.advance()
        if next_path is None:
            if self._session:
                await self._session.stop()
                self._session = None
            self.after(0, self._reset_playing)
            self.after(0, self._set_status, "Playlist finished.")
            return

        self.after(0, self._update_now_playing)
        self.after(0, self._update_playlist_display)

        try:
            url = await self._streamer.start(next_path)
            await self._session.stream(url)
            self.after(0, self._set_status, f"Playing: {os.path.basename(next_path)}")
            self._session.start_push_updates(
                lambda ds, pos, dur: self.after(0, self._on_device_state, ds, pos, dur)
            )
            self._poll_task = asyncio.ensure_future(self._poll_position())
        except Exception as exc:
            if self._session:
                self._session.close()
                self._session = None
            await self._streamer.stop()
            self.after(0, self._set_status, f"Error: {exc}")
            self.after(0, self._reset_playing)

    async def _jump_to_track(self, index: int):
        """Mid-playback: switch to a specific playlist index."""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        await self._streamer.stop()
        self._playlist.select(index)
        path = self._playlist.current
        self.after(0, self._update_now_playing)
        self.after(0, self._update_playlist_display)

        try:
            url = await self._streamer.start(path)
            await self._session.stream(url)
            self.after(0, self._set_status, f"Playing: {os.path.basename(path)}")
            self._session.start_push_updates(
                lambda ds, pos, dur: self.after(0, self._on_device_state, ds, pos, dur)
            )
            self._poll_task = asyncio.ensure_future(self._poll_position())
        except Exception as exc:
            self.after(0, self._set_status, f"Error: {exc}")

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
        if state == DeviceState.Paused and not self._paused:
            self._set_paused_ui(True)
        elif state == DeviceState.Playing and self._paused:
            self._set_paused_ui(False)
        elif state in (DeviceState.Stopped, DeviceState.Idle) and self._playing:
            if not self._mirror_mode and self._playlist.has_next():
                self._run_async(self._advance_and_play())
            else:
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
        self._update_playlist_display()
        self._refresh_play_state()

    # ------------------------------------------------------------------
    # Public API (IPC / context menu)
    # ------------------------------------------------------------------

    def open_file(self, path: str) -> None:
        """Add a file to the playlist — called from CLI argument or IPC handoff."""
        self._playlist.add(path)
        self._update_playlist_display()
        self._update_now_playing()
        if self._mirror_switch.get():
            self._mirror_switch.deselect()
            self._on_mirror_toggle()
        self._refresh_play_state()
        self.deiconify()
        self.lift()
        self.focus_force()

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
