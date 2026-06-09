from __future__ import annotations

import os
from pathlib import Path

# 프로젝트 루트 = .../SNS 다운로더
ROOT = Path(__file__).resolve().parents[2]

HOME = Path.home()

# 쿠키 파일을 자동으로 찾는 위치들 (위에서부터 우선)
_SEARCH_DIRS = [
    HOME / "Desktop" / "SNS 다운로드",   # 권장 위치
    HOME / "Desktop",
    HOME / "Downloads",                  # 브라우저 확장이 내보내는 기본 위치
    ROOT,
]

# 매칭할 파일명 패턴 (확장 프로그램마다 이름이 조금씩 다름)
_COOKIE_GLOBS = ["cookies.txt", "*cookies*.txt", "*.x.com*cookies*.txt"]


def _find_cookie_file() -> Path | None:
    candidates: list[Path] = []
    for d in _SEARCH_DIRS:
        if not d.exists():
            continue
        for pat in _COOKIE_GLOBS:
            candidates.extend(d.glob(pat))
    # 중복 제거 후 가장 최근에 수정된 파일 선택
    uniq = {str(p): p for p in candidates if p.is_file()}
    if not uniq:
        return None
    return max(uniq.values(), key=lambda p: p.stat().st_mtime)


def cookie_opts() -> dict:
    """yt-dlp에 넘길 쿠키 옵션을 반환한다.

    우선순위:
      1) 환경변수 YTDLP_COOKIES = cookies.txt 파일 경로
      2) 바탕화면/다운로드 폴더 등에서 cookies 파일 자동 탐색 (가장 최근 것)
      3) 환경변수 YTDLP_COOKIES_FROM_BROWSER = chrome | edge | firefox ...

    아무것도 없으면 빈 dict (= 비로그인, 기존 동작 그대로).
    """
    env_file = os.environ.get("YTDLP_COOKIES", "").strip()
    if env_file and Path(env_file).expanduser().exists():
        return {"cookiefile": str(Path(env_file).expanduser())}

    found = _find_cookie_file()
    if found:
        return {"cookiefile": str(found)}

    browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip().lower()
    if browser:
        return {"cookiesfrombrowser": (browser,)}

    return {}
