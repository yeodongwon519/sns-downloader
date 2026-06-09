"""X(트위터) 로그인 쿠키를 Chrome에서 추출해 cookies.txt로 저장.

관리자 권한으로 실행해야 한다 (최신 Chrome App-Bound Encryption 복호화에 필요).
Desktop의 'X-쿠키-추출' 실행 파일이 이 스크립트를 관리자 권한으로 호출한다.
모든 처리는 로컬 PC 안에서만 일어나며 외부로 전송되지 않는다.
"""
from __future__ import annotations

import glob
import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import time

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
OUT = os.path.join(DESKTOP, "SNS 다운로드", "cookies.txt")
LOG = os.path.join(DESKTOP, "쿠키추출-로그.txt")
BASE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")

_logf = None


def log(msg: str):
    print(msg)
    if _logf:
        _logf.write(msg + "\n")
        _logf.flush()


def find_login_profile() -> str | None:
    """x.com auth_token 쿠키가 들어있는 Chrome 프로필 폴더명을 찾는다 (값 복호화 없이 메타만)."""
    profiles = ["Default"] + [os.path.basename(p) for p in glob.glob(os.path.join(BASE, "Profile *"))]
    for prof in profiles:
        db = os.path.join(BASE, prof, "Network", "Cookies")
        if not os.path.exists(db):
            continue
        tmp = os.path.join(tempfile.gettempdir(), f"ckchk_{prof}.db")
        try:
            shutil.copy2(db, tmp)
            con = sqlite3.connect(tmp)
            row = con.execute(
                "select count(*) from cookies where host_key like '%x.com%' and name='auth_token'"
            ).fetchone()
            con.close()
            if row and row[0] > 0:
                return prof
        except Exception:
            pass
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return None


def main() -> int:
    log("=" * 40)
    log("  X 쿠키 추출 시작")
    log("=" * 40)

    try:
        import rookiepy
    except ImportError:
        log("[오류] rookiepy 미설치. 'pip install rookiepy' 필요.")
        return 1

    # Chrome 종료 (쿠키 DB 잠금 해제)
    log("[1] Chrome 종료 중...")
    subprocess.run(["taskkill", "/im", "chrome.exe", "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # 로그인된 프로필 탐색
    prof = find_login_profile()
    if not prof:
        log("[오류] x.com 에 로그인된 Chrome 프로필을 찾지 못했습니다.")
        log("       Chrome에서 x.com 에 로그인되어 있는지 확인하세요.")
        return 1
    log(f"[2] 로그인 프로필 발견: {prof}")

    key_path = os.path.join(BASE, "Local State")
    db_path = os.path.join(BASE, prof, "Network", "Cookies")

    log("[3] 쿠키 복호화 중 (관리자 권한 필요)...")
    try:
        cookies = rookiepy.chromium_based(key_path, db_path, [".x.com", ".twitter.com"])
    except Exception as e:
        log(f"[오류] 복호화 실패: {str(e)[:200]}")
        log("       → 관리자 권한으로 실행했는지 확인하세요.")
        return 1

    names = {c.get("name") for c in cookies}
    log(f"[4] 쿠키 {len(cookies)}개 추출 (auth_token={'auth_token' in names}, ct0={'ct0' in names})")
    if "auth_token" not in names:
        log("[경고] auth_token 없음 — 로그인 상태가 아닐 수 있습니다.")
        if not cookies:
            return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    netscape = rookiepy.to_netscape(cookies)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(netscape)
    log(f"[5] 저장 완료 → {OUT}")
    log("")
    log("★ 성공! 이제 SNS Downloader에서 X 영상을 다시 받아보세요.")
    log("  (Chrome 다시 열어도 됩니다)")
    return 0


if __name__ == "__main__":
    try:
        _logf = open(LOG, "w", encoding="utf-8")
    except Exception:
        _logf = None
    try:
        code = main()
    except Exception as e:
        log(f"[예외] {e}")
        code = 1
    finally:
        if _logf:
            _logf.close()
    try:
        input("\n엔터 키를 누르면 창이 닫힙니다...")
    except Exception:
        pass
    sys.exit(code)
