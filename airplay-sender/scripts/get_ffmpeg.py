"""
Downloads the latest ffmpeg Windows static build (BtbN GitHub release) and
extracts ffmpeg.exe into the airplay-sender/ directory ready for PyInstaller.

Usage:
    python scripts/get_ffmpeg.py
"""

import io
import os
import sys
import urllib.request
import zipfile

# BtbN publishes nightly static Windows builds on GitHub.
# The 'latest' redirect always points to the most recent release.
RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
ASSET_SUFFIX = "ffmpeg-master-latest-win64-gpl.zip"

DEST_DIR = os.path.join(os.path.dirname(__file__), "..")  # airplay-sender/
DEST = os.path.join(DEST_DIR, "ffmpeg.exe")


def _find_asset_url() -> str:
    req = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "win-airplay-setup"},
    )
    with urllib.request.urlopen(req) as resp:
        import json
        data = json.load(resp)

    for asset in data.get("assets", []):
        if asset["name"].endswith(ASSET_SUFFIX):
            return asset["browser_download_url"]

    raise RuntimeError(
        f"Could not find asset ending with '{ASSET_SUFFIX}' in the latest release.\n"
        "Check https://github.com/BtbN/FFmpeg-Builds/releases for current filenames."
    )


def _download(url: str) -> bytes:
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "win-airplay-setup"})

    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunks = []
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"\r  {pct:3d}%  {downloaded // 1_048_576} / {total // 1_048_576} MB", end="", flush=True)
        print()
        return b"".join(chunks)


def main():
    if os.path.isfile(DEST):
        print(f"ffmpeg.exe already present at {os.path.abspath(DEST)} — nothing to do.")
        return

    print("Fetching latest release metadata from BtbN/FFmpeg-Builds …")
    url = _find_asset_url()

    data = _download(url)

    print("Extracting ffmpeg.exe …")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # The zip contains a top-level folder; ffmpeg.exe is in its bin/ subdirectory.
        candidates = [n for n in zf.namelist() if n.endswith("/bin/ffmpeg.exe")]
        if not candidates:
            raise RuntimeError("ffmpeg.exe not found in the downloaded zip.")

        with zf.open(candidates[0]) as src, open(DEST, "wb") as dst:
            dst.write(src.read())

    print(f"Done — ffmpeg.exe written to {os.path.abspath(DEST)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
