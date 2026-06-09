from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from yt_dlp import YoutubeDL

from ._cookies import cookie_opts

ProgressCB = Optional[Callable[[dict], None]]

_YT_RE = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|live/|embed/)|youtu\.be/)",
    re.IGNORECASE,
)


def is_youtube_url(url: str) -> bool:
    return bool(_YT_RE.search((url or "").strip()))


def download_youtube(url: str, out_dir: Path, on_progress: ProgressCB = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def emit(progress=None, stage=None, current=None):
        if on_progress:
            on_progress({"progress": progress, "stage": stage, "current": current})

    emit(progress=0, stage="준비 중")

    saved: dict = {"path": None}

    def hook(d: dict):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 95) if total else None
            emit(progress=pct, stage="다운로드 중", current=d.get("filename"))
        elif status == "finished":
            saved["path"] = d.get("filename")
            emit(progress=96, stage="후처리 중", current=d.get("filename"))

    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).200B [%(id)s].%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "restrictfilenames": False,
        "windowsfilenames": True,
        **cookie_opts(),  # cookies.txt 있으면 로그인 상태로 받음 (연령제한/멤버십)
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # When merged/postprocessed, the real path comes from prepare_filename
        # adjusted to the final container.
        final = ydl.prepare_filename(info)
        final_path = Path(final)
        if not final_path.exists():
            # merge may have changed extension to mp4
            alt = final_path.with_suffix(".mp4")
            if alt.exists():
                final_path = alt
            elif saved["path"] and Path(saved["path"]).exists():
                final_path = Path(saved["path"])

    emit(progress=100, stage="완료", current=final_path.name)

    return {
        "filepath": str(final_path),
        "title": (info or {}).get("title"),
        "id": (info or {}).get("id"),
    }
