# Win-AirPlay

A standalone Windows desktop app for streaming local video files to an Apple TV over AirPlay.

Pick a file, pick a device, hit Play — ffmpeg transcodes on the fly while a local HTTP server feeds the stream to your Apple TV.

---

## Features

- Auto-discovers Apple TV devices on the local network via mDNS
- Supports any video format ffmpeg can read (MP4, MKV, MOV, AVI, etc.)
- Re-encodes to H.264 + AAC for guaranteed Apple TV compatibility
- Handles first-run AirPlay pairing with a PIN dialog
- Clean stop: kills the transcoder, shuts down the HTTP server, and stops playback on the device

---

## Requirements

- Windows 10/11 (or macOS/Linux for development)
- Python 3.10+
- Apple TV on the same local network

> ffmpeg is downloaded automatically by the setup script (see below). You do not need to install it manually.

---

## Installation

```bash
git clone https://github.com/kampfz/Win-Airplay.git
cd Win-Airplay/airplay-sender
pip install -r requirements.txt
python scripts/get_ffmpeg.py
```

`get_ffmpeg.py` downloads the latest Windows static ffmpeg build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases) and extracts `ffmpeg.exe` into `airplay-sender/`. It is a no-op if the file already exists.

---

## Usage

```bash
python main.py
```

1. The app scans for Apple TV devices on launch — they appear in the dropdown.
2. Click **Browse** to select a video file.
3. Select your Apple TV from the dropdown and click **Play**.
4. On first use, your Apple TV will display a pairing PIN — enter it in the dialog that appears.
5. Click **Stop** to end playback and clean up.

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
```

| Component | Role |
|---|---|
| `services/discovery.py` | Async mDNS scan via `pyatv.scan()` |
| `services/streamer.py` | Spawns ffmpeg, waits for first segment, serves HLS over HTTP |
| `services/airplay.py` | Connects to Apple TV, handles AirPlay pairing, calls `stream_file()` |
| `gui/app.py` | customtkinter UI; all async work runs on a background event loop |

---

## Building a standalone .exe

ffmpeg is bundled automatically into the exe. Run the setup script first if you haven't already, then build:

```bash
python scripts/get_ffmpeg.py   # downloads ffmpeg.exe if not present
pip install pyinstaller
pyinstaller airplay-sender/build.spec
```

The output is `dist/WinAirPlay.exe`. ffmpeg is embedded inside it — no separate install needed on the target machine.

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

**Buffering / poor quality**
- The default preset is `veryfast`; adjust `-preset` in `services/streamer.py` for a quality/speed tradeoff.

---

## License

MIT
