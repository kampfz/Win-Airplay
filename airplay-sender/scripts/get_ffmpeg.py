"""
Downloads the latest ffmpeg Windows static build (BtbN GitHub release) and
extracts ffmpeg.exe into a target directory.

Can be run standalone:
    python scripts/get_ffmpeg.py

Or imported and called programmatically:
    from scripts.get_ffmpeg import ensure_ffmpeg
    ffmpeg_path = ensure_ffmpeg(dest_dir, progress_cb=lambda pct: ...)
"""

import io
import json
import os
import sys
import urllib.request
import zipfile
from typing import Callable, Optional

RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
ASSET_SUFFIX = "ffmpeg-master-latest-win64-gpl.zip"

# Default destination: airplay-sender/ (parent of scripts/)
_DEFAULT_DEST_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def ensure_ffmpeg(
    dest_dir: str = _DEFAULT_DEST_DIR,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> str:
    """Return the path to ffmpeg.exe, downloading it first if necessary.

    *progress_cb* is called with an integer 0-100 during the download.
    """
    dest = os.path.join(dest_dir, "ffmpeg.exe")
    if os.path.isfile(dest):
        return dest

    url = _find_asset_url()
    data = _download(url, progress_cb)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        candidates = [n for n in zf.namelist() if n.endswith("/bin/ffmpeg.exe")]
        if not candidates:
            raise RuntimeError("ffmpeg.exe not found inside the downloaded archive.")
        with zf.open(candidates[0]) as src, open(dest, "wb") as dst:
            dst.write(src.read())

    return dest


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _find_asset_url() -> str:
    req = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "win-airplay-setup"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)

    for asset in data.get("assets", []):
        if asset["name"].endswith(ASSET_SUFFIX):
            return asset["browser_download_url"]

    raise RuntimeError(
        f"Could not find asset ending with '{ASSET_SUFFIX}' in the latest release.\n"
        "Check https://github.com/BtbN/FFmpeg-Builds/releases for available filenames."
    )


def _download(url: str, progress_cb: Optional[Callable[[int], None]]) -> bytes:
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
            if progress_cb and total:
                progress_cb(downloaded * 100 // total)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli():
    dest = ensure_ffmpeg(
        progress_cb=lambda pct: print(f"\r  {pct:3d}%", end="", flush=True)
    )
    print(f"\nDone — {dest}")


if __name__ == "__main__":
    try:
        _cli()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
