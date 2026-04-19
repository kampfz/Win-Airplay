# Win-AirPlay

A standalone Windows desktop app for streaming local video files to an Apple TV over AirPlay.

Pick a file, pick a device, hit Play — ffmpeg transcodes on the fly while a local HTTP server feeds the stream to your Apple TV.

---

## Features

- Auto-discovers Apple TV devices on the local network via mDNS
- Supports any video format ffmpeg can read (MP4, MKV, MOV, AVI, etc.)
- Re-encodes to H.264 + AAC for guaranteed Apple TV compatibility
- Handles first-run AirPlay pairing with a PIN dialog
- Play, Pause/Resume, and Stop controls in the app
- Seek bar with live time display; drag to jump to any position
- GUI stays in sync when you use the Apple TV remote, Siri, or Control Centre
- **Screen mirroring** — toggle a switch to stream your Windows desktop live to Apple TV
- **System tray** — closing the window hides to tray; right-click the tray icon to Show, Stop, or Quit
- Clean stop: kills the transcoder, shuts down the HTTP server, and removes temp files

---

## Requirements

- Windows 10/11 (or macOS/Linux for development)
- Python 3.10+
- Apple TV on the same local network

> ffmpeg is downloaded automatically on first launch. You do not need to install it manually.

---

## Installation

```bash
git clone https://github.com/kampfz/Win-Airplay.git
cd Win-Airplay/airplay-sender
pip install -r requirements.txt
python main.py
```

On the very first launch, a small progress dialog downloads the latest Windows static ffmpeg build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases) into `airplay-sender/ffmpeg.exe`. Subsequent launches skip this step entirely.

---

## Usage

```bash
python main.py
```

1. The app scans for Apple TV devices on launch — they appear in the dropdown.
2. Click **Browse** to select a video file.
3. Select your Apple TV and click **▶ Play**.
4. On first use, your Apple TV will display a pairing PIN — enter it in the dialog that appears.
5. Use **⏸ Pause** to pause; the button label changes to **▶ Resume**. Click again to resume.
6. Drag the seek bar to jump to a position; the time label updates live while dragging.
7. Click **■ Stop** to end playback and clean up.

Changes made from the Apple TV remote, Siri, or Control Centre are reflected in the GUI automatically — the pause button and seek bar stay in sync.

Use **Rescan** at any time to refresh the device list.

### Screen mirroring

Toggle the **Mirror screen** switch before hitting Play. The app captures your Windows desktop via ffmpeg and streams it live to Apple TV. The file picker is disabled in this mode. Note: seek and position tracking are not available during a live mirror session.

### System tray

Clicking the window's close button hides the app to the system tray rather than quitting. Right-click the tray icon for options:

| Option | Action |
|---|---|
| Show | Restore the window |
| Stop Playback | Stop the current stream |
| Quit | Stop playback and exit |

### Right-click context menu

After building the `.exe`, register a Windows Explorer context menu entry so you can right-click any video file and choose **AirPlay to Apple TV**:

```bash
python scripts/register_context_menu.py install
# or point explicitly:
python scripts/register_context_menu.py install "C:\path\to\WinAirPlay.exe"
```

To remove it:

```bash
python scripts/register_context_menu.py uninstall
```

No administrator rights are required — entries are written to `HKCU`. If Win-AirPlay is already running in the tray, right-clicking a file will bring its window to the front with that file pre-selected rather than launching a second instance.

---

## How it works

```
Video file
    │
    ▼
ffmpeg  ──►  HLS segments (.ts) + playlist (.m3u8)  in a temp dir
                        │
                        ▼
               aiohttp HTTP server  (http://[local-ip]:[random-port]/)
                        │
                        ▼
              pyatv  stream_file()  ──►  Apple TV fetches & plays stream
                        │
              ◄─── push_updater ────────  Apple TV sends state changes
```

| Component | Role |
|---|---|
| `services/discovery.py` | Async mDNS scan via `pyatv.scan()` |
| `services/streamer.py` | Spawns ffmpeg, waits for first segment, serves HLS over HTTP |
| `services/airplay.py` | `AirPlaySession` — persistent pyatv connection with pause, resume, seek, and push update listener |
| `gui/app.py` | customtkinter UI with seek bar, mirror switch, and system tray |
| `scripts/get_ffmpeg.py` | Downloads ffmpeg on first run |

---

## Building a standalone .exe

ffmpeg is bundled automatically into the exe. Launch the app once first so it downloads `ffmpeg.exe`, then build:

```bash
python main.py                 # downloads ffmpeg.exe on first run, then quit
pip install pyinstaller
pyinstaller airplay-sender/build.spec
```

The output is `dist/WinAirPlay.exe` — no separate ffmpeg install needed on the target machine.

---

## Troubleshooting

**No devices found**
- Confirm the Apple TV is on and on the same Wi-Fi network.
- Check that your firewall isn't blocking mDNS (UDP port 5353).
- Click **Rescan**.

**Pairing fails**
- Make sure you enter the PIN within a few seconds of it appearing on the TV.
- Delete any stale credentials stored by pyatv and try again.

**Video won't play / black screen**
- Re-run `python scripts/get_ffmpeg.py` to ensure `ffmpeg.exe` is present.
- Check that the source file isn't DRM-protected.

**Pause/seek not working from the app**
- These use AirPlay remote control commands; they require a successful pairing. Try stopping and replaying.

**GUI not reflecting Apple TV remote changes**
- Push updates require an active AirPlay connection. If the device dropped the connection, stop and restart playback.

**Buffering / poor quality**
- For file playback, the default preset is `veryfast`; adjust `-preset` in `services/streamer.py` for a quality/speed tradeoff.
- Screen mirroring uses `ultrafast` + `zerolatency` and 2-second HLS segments; expect 4–8 seconds of end-to-end latency.

**Screen mirroring not working**
- `gdigrab` is Windows-only. On macOS use `-f avfoundation`, on Linux use `-f x11grab`.
- Make sure no DRM or hardware overlay is blocking capture (e.g. some video players render to a protected surface).

---

## License

MIT
