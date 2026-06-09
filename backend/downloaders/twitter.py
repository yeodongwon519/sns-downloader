from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from yt_dlp import YoutubeDL

from ._cookies import cookie_opts

ProgressCB = Optional[Callable[[dict], None]]

_TW_RE = re.compile(
    r"^(https?://)?(www\.|mobile\.)?"
    r"(twitter\.com|x\.com)/[^/]+/status/\d+",
    re.IGNORECASE,
)


def is_twitter_url(url: str) -> bool:
    return bool(_TW_RE.search((url or "").strip()))


def download_twitter(url: str, out_dir: Path, on_progress: ProgressCB = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def emit(progress=None, stage=None, current=None):
        if on_progress:
            on_progress({"progress": progress, "stage": stage, "current": current})

    emit(progress=0, stage="준비 중")

    _MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".gif"}

    def snapshot() -> dict[str, float]:
        return {
            str(p): p.stat().st_mtime
            for p in out_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in _MEDIA_EXTS
        }

    before = snapshot()

    def hook(d: dict):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 95) if total else None
            emit(progress=pct, stage="다운로드 중", current=d.get("filename"))
        elif status == "finished":
            emit(progress=96, stage="후처리 중", current=d.get("filename"))

    co = cookie_opts()  # cookies.txt 있으면 로그인 상태로 받음
    has_cookie = "cookiefile" in co or "cookiesfrombrowser" in co

    ydl_opts = {
        "outtmpl": str(out_dir / "%(uploader_id)s %(id)s %(autonumber)s.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "windowsfilenames": True,
        **co,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        msg = str(e)
        # X는 이제 영상 추출에 로그인을 강제한다. 쿠키 없이 실패하면 원인을 명확히 안내.
        login_walled = (
            "No video could be found" in msg
            or "NSFW" in msg
            or "age-restricted" in msg.lower()
            or "Unable to download" in msg
            or "log in" in msg.lower()
            or "logged in" in msg.lower()
        )
        if not has_cookie and login_walled:
            raise Exception(
                "X(트위터)는 이제 영상 다운로드에 로그인이 필요합니다. "
                "쿠키가 없어 X가 영상을 내주지 않았어요. "
                "바탕화면 'SNS 다운로드' 폴더에 cookies.txt를 넣으면 자동으로 인식합니다. "
                "(크롬 확장 'Get cookies.txt LOCALLY'로 x.com 쿠키를 내보내거나 grab_cookies_cdp.py 실행)"
            )
        raise

    # Reliable file detection: diff the output folder before/after. Catches the
    # final merged container regardless of extension changes during postprocess.
    after = snapshot()
    new_files = sorted(
        p for p, m in after.items() if p not in before or m != before.get(p)
    )

    emit(progress=100, stage="완료")

    return {
        "files": new_files,
        "id": (info or {}).get("id"),
    }
