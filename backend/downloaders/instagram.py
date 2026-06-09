from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

import instaloader
from instaloader import Instaloader, Profile
from instaloader.exceptions import (
    TwoFactorAuthRequiredException,
    BadCredentialsException,
    ConnectionException,
)

ProgressCB = Optional[Callable[[dict], None]]

ROOT = Path(__file__).resolve().parents[2]
SESSIONS = ROOT / "sessions"

_MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".gif"}

_POST_RE = re.compile(
    r"^(https?://)?(www\.)?instagram\.com/(p|reel|reels|tv)/[\w\-]+",
    re.IGNORECASE,
)


def is_instagram_post_url(url: str) -> bool:
    return bool(_POST_RE.search((url or "").strip()))


def _shortcode_from_url(url: str) -> Optional[str]:
    m = re.search(r"instagram\.com/(?:p|reel|reels|tv)/([\w\-]+)", url or "", re.IGNORECASE)
    return m.group(1) if m else None


def _new_session(login_user: str) -> Instaloader:
    L = Instaloader(
        quiet=True,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
    )
    return L


def _login(L: Instaloader, login_user: str, login_pass: str, two_factor_code: Optional[str]):
    """Login, reusing a saved session when possible. Raises Exception('2FA_REQUIRED')
    when a 2FA code is needed and none was provided."""
    SESSIONS.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS / f"{login_user}.json"

    if session_file.exists() and not two_factor_code:
        try:
            L.load_session_from_file(login_user, str(session_file))
            # Validate the session is actually logged in.
            if L.test_login() == login_user:
                return
        except Exception:
            pass  # fall through to a fresh login

    try:
        if two_factor_code:
            # Re-attempt: instaloader needs the username/password attempt first
            # to arm two_factor_login. We trigger the 2FA path then submit.
            try:
                L.login(login_user, login_pass)
            except TwoFactorAuthRequiredException:
                L.two_factor_login(two_factor_code)
        else:
            L.login(login_user, login_pass)
    except TwoFactorAuthRequiredException:
        raise Exception("2FA_REQUIRED")
    except BadCredentialsException:
        raise Exception("로그인 정보가 올바르지 않습니다.")
    except ConnectionException as e:
        msg = str(e)
        if "two-factor" in msg.lower() or "2fa" in msg.lower():
            raise Exception("2FA_REQUIRED")
        raise Exception(f"인스타그램 연결 오류: {msg[:200]}")

    try:
        L.save_session_to_file(str(session_file))
    except Exception:
        pass


def _snapshot(dirpath: Path) -> set[str]:
    if not dirpath.exists():
        return set()
    return {str(p) for p in dirpath.rglob("*") if p.suffix.lower() in _MEDIA_EXTS}


def _collect_new(dirpath: Path, before: set[str]) -> list[str]:
    after = _snapshot(dirpath)
    new = sorted(after - before)
    return new


def download_instagram(
    target: str,
    login_user: str,
    login_pass: str,
    out_dir: Path,
    include_posts: bool = True,
    include_highlights: bool = True,
    two_factor_code: Optional[str] = None,
    on_progress: ProgressCB = None,
) -> dict:
    out_dir = Path(out_dir)
    target = target.strip().lstrip("@")
    target_dir = out_dir / target
    target_dir.mkdir(parents=True, exist_ok=True)

    def emit(progress=None, stage=None, current=None):
        if on_progress:
            on_progress({"progress": progress, "stage": stage, "current": current})

    emit(progress=0, stage="로그인 중")

    L = _new_session(login_user)
    L.dirname_pattern = str(target_dir)
    _login(L, login_user, login_pass, two_factor_code)

    before = _snapshot(target_dir)

    emit(progress=5, stage="프로필 조회 중", current=target)
    try:
        profile = Profile.from_username(L.context, target)
    except Exception as e:
        raise Exception(f"대상 계정을 찾을 수 없습니다: {str(e)[:200]}")

    if include_posts:
        total = profile.mediacount or 0
        done = 0
        emit(progress=8, stage="게시물 다운로드 중", current=f"0/{total}")
        for post in profile.get_posts():
            try:
                L.download_post(post, target=target)
            except Exception:
                pass
            done += 1
            pct = 8 + (done / total * 82) if total else None
            emit(progress=pct, stage="게시물 다운로드 중", current=f"{done}/{total}")

    if include_highlights:
        emit(progress=92, stage="하이라이트 다운로드 중", current=target)
        try:
            for highlight in L.get_highlights(profile):
                for item in highlight.get_items():
                    try:
                        L.download_storyitem(item, target=target)
                    except Exception:
                        pass
        except Exception:
            # Highlights can fail (private/none); not fatal.
            pass

    files = _collect_new(target_dir, before)
    emit(progress=100, stage="완료", current=f"{len(files)}개 파일")

    return {"files": files, "target": target, "count": len(files)}


def download_instagram_post(
    url: str,
    login_user: str,
    login_pass: str,
    out_dir: Path,
    two_factor_code: Optional[str] = None,
    on_progress: ProgressCB = None,
) -> dict:
    out_dir = Path(out_dir)
    shortcode = _shortcode_from_url(url)
    if not shortcode:
        raise Exception("게시물 URL에서 코드를 추출할 수 없습니다.")

    post_dir = out_dir / "_posts"
    post_dir.mkdir(parents=True, exist_ok=True)

    def emit(progress=None, stage=None, current=None):
        if on_progress:
            on_progress({"progress": progress, "stage": stage, "current": current})

    emit(progress=0, stage="로그인 중")

    L = _new_session(login_user)
    L.dirname_pattern = str(post_dir)
    _login(L, login_user, login_pass, two_factor_code)

    before = _snapshot(post_dir)

    emit(progress=30, stage="게시물 조회 중", current=shortcode)
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise Exception(f"게시물을 불러올 수 없습니다: {str(e)[:200]}")

    emit(progress=50, stage="다운로드 중", current=shortcode)
    L.download_post(post, target="_posts")

    files = _collect_new(post_dir, before)
    emit(progress=100, stage="완료", current=f"{len(files)}개 파일")

    return {"files": files, "shortcode": shortcode, "count": len(files)}
