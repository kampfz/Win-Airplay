"""Transcodes a video file to HLS via ffmpeg and serves it over HTTP with aiohttp."""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Optional

from aiohttp import web


class HLSStreamer:
    def __init__(self):
        self._tmpdir: Optional[str] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._runner: Optional[web.AppRunner] = None
        self._port: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, video_path: str) -> str:
        """Transcode *video_path* to HLS and start HTTP server. Returns stream URL."""
        self._tmpdir = tempfile.mkdtemp(prefix="airplay_hls_")
        self._port = self._free_port()

        self._start_ffmpeg(video_path)
        await self._wait_for_playlist()
        await self._start_http_server()

        local_ip = self._local_ip()
        return f"http://{local_ip}:{self._port}/stream.m3u8"

    async def stop(self):
        """Kill ffmpeg, stop HTTP server, and clean up temp files."""
        if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
            self._ffmpeg_proc.terminate()
            try:
                self._ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ffmpeg_proc.kill()
        self._ffmpeg_proc = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        if self._tmpdir and os.path.isdir(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        self._tmpdir = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _ffmpeg_bin() -> str:
        # When running from a PyInstaller bundle, ffmpeg.exe is extracted
        # alongside the exe in sys._MEIPASS; fall back to PATH otherwise.
        if hasattr(sys, "_MEIPASS"):
            candidate = os.path.join(sys._MEIPASS, "ffmpeg.exe")
            if os.path.isfile(candidate):
                return candidate
        return "ffmpeg"

    def _start_ffmpeg(self, video_path: str):
        playlist = os.path.join(self._tmpdir, "stream.m3u8")
        segment = os.path.join(self._tmpdir, "seg%03d.ts")

        cmd = [
            self._ffmpeg_bin(),
            "-y",
            "-i", video_path,
            # Video: H.264 baseline for maximum Apple TV compatibility
            "-c:v", "libx264",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-preset", "veryfast",
            # Audio: AAC stereo
            "-c:a", "aac",
            "-b:a", "192k",
            "-ac", "2",
            # HLS muxer
            "-f", "hls",
            "-hls_time", "4",
            "-hls_list_size", "0",
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", segment,
            playlist,
        ]

        self._ffmpeg_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def _wait_for_playlist(self, timeout: float = 30.0):
        """Block until ffmpeg has written at least one segment into the playlist."""
        playlist = os.path.join(self._tmpdir, "stream.m3u8")
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            if os.path.exists(playlist) and os.path.getsize(playlist) > 0:
                # Playlist exists; make sure at least one .ts segment is referenced
                with open(playlist) as f:
                    if ".ts" in f.read():
                        return
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError("ffmpeg did not produce HLS output in time.")
            await asyncio.sleep(0.5)

    async def _start_http_server(self):
        app = web.Application()
        app.router.add_static("/", self._tmpdir)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    @staticmethod
    def _local_ip() -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
            except OSError:
                return "127.0.0.1"
