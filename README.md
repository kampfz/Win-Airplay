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
- GUI stays in sync when you use the Apple TV remote, Siri, or Control Centre — pause, resume, and stop events all reflect immediately
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
| `gui/app.py` | customtkinter UI with seek bar; syncs with Apple TV via push callbacks |
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
- The default preset is `veryfast`; adjust `-preset` in `services/streamer.py` for a quality/speed tradeoff.

---

## License

MIT
