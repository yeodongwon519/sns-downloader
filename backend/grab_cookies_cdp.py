"""Chrome을 임시 프로필 사본으로 잠깐 띄워서, X 로그인 쿠키를 CDP로 받아 cookies.txt 저장.

App-Bound Encryption(최신 Chrome)을 우회한다: 복호화는 Chrome 자신이 수행하고,
우리는 DevTools Protocol(Network.getAllCookies)로 이미 복호화된 쿠키를 받는다.
관리자 권한 불필요. 모든 처리는 로컬 PC 안에서만.

프로필 자동 탐지: CHROME_PROFILE 환경변수가 없으면, x.com 로그인(auth_token)이
들어있는 크롬 프로필을 스스로 찾아 사용한다. (쿠키 '이름'은 평문이라 값 복호화 없이 탐지 가능)
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

# Chrome 실행 파일 후보 (설치 위치가 환경마다 다름)
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
]
BASE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "SNS 다운로드", "cookies.txt")
PORT = 9777


def find_chrome() -> str | None:
    for p in _CHROME_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def profile_has_x_login(cookies_db: str) -> bool:
    """프로필의 Cookies DB에 x.com auth_token이 있는지 검사.
    값(value)은 암호화돼 있지만 이름(name)은 평문이라 존재 여부만 확인 가능."""
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(cookies_db, tmp)
        con = sqlite3.connect(tmp)
        try:
            cur = con.execute(
                "SELECT 1 FROM cookies "
                "WHERE host_key LIKE '%x.com%' AND name='auth_token' LIMIT 1"
            )
            return cur.fetchone() is not None
        finally:
            con.close()
    except Exception:
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def detect_profile() -> str | None:
    """x.com 로그인된 프로필 디렉터리명을 반환. (Chrome 종료 후 호출해야 DB 잠김 없음)
    여러 개면 가장 최근에 수정된 것을 우선."""
    env = os.environ.get("CHROME_PROFILE", "").strip()
    if env:
        return env

    matches = []
    for prof_dir in glob.glob(os.path.join(BASE, "*")):
        ck = os.path.join(prof_dir, "Network", "Cookies")
        if os.path.isfile(ck) and profile_has_x_login(ck):
            matches.append((os.path.getmtime(ck), os.path.basename(prof_dir)))
    if not matches:
        return None
    matches.sort(reverse=True)  # 최근 사용 프로필 우선
    return matches[0][1]


def main() -> int:
    chrome = find_chrome()
    if not chrome:
        print("chrome.exe를 찾을 수 없습니다. Chrome이 설치돼 있는지 확인하세요.")
        return 1

    # 1) 잠금 해제 + 프로필 탐지를 위해 Chrome 종료
    print("크롬을 잠시 닫습니다... (쿠키 추출 후 다시 열면 됩니다)")
    subprocess.run(["taskkill", "/im", "chrome.exe", "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # 2) x.com 로그인된 프로필 자동 탐지
    profile = detect_profile()
    if not profile:
        print("x.com 로그인된 크롬 프로필을 찾지 못했습니다.")
        print(" → 크롬에서 x.com 에 로그인한 뒤 이 파일을 다시 실행하세요.")
        print(" → 특정 프로필을 지정하려면 환경변수 CHROME_PROFILE 을 설정하세요. (예: \"Profile 1\")")
        return 1
    print(f"사용할 프로필: {profile}")

    src_cookies = os.path.join(BASE, profile, "Network", "Cookies")

    # 3) 임시 user-data-dir에 필요한 파일만 복사 (Local State = ABE 키, 해당 프로필 쿠키)
    tmp = tempfile.mkdtemp(prefix="snsdl_chrome_")
    try:
        shutil.copy2(os.path.join(BASE, "Local State"), os.path.join(tmp, "Local State"))
        netdir = os.path.join(tmp, "Default", "Network")
        os.makedirs(netdir, exist_ok=True)
        shutil.copy2(src_cookies, os.path.join(netdir, "Cookies"))

        # 4) 임시 프로필로 Chrome 기동 (원래 Chrome과 별개 인스턴스) + 원격 디버깅
        args = [
            chrome,
            f"--user-data-dir={tmp}",
            f"--remote-debugging-port={PORT}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-extensions",
            "--window-position=-32000,-32000",
            "about:blank",
        ]
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 5) DevTools 엔드포인트 대기
        ws_url = None
        for _ in range(40):
            try:
                data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1))
                for t in data:
                    if t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not ws_url:
            print("DevTools에 연결하지 못했습니다.")
            proc.kill()
            return 1

        # 6) Network.getAllCookies 호출 (복호화된 전체 쿠키 반환)
        try:
            import websocket  # websocket-client
        except ImportError:
            print("websocket-client 모듈이 없습니다.  pip install websocket-client  후 다시 실행하세요.")
            proc.kill()
            return 1
        ws = websocket.create_connection(ws_url, timeout=15, max_size=None)
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        cookies = []
        for _ in range(50):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                cookies = (msg.get("result") or {}).get("cookies", [])
                break
        ws.close()
        proc.kill()

        target = [c for c in cookies if "x.com" in c.get("domain", "") or "twitter.com" in c.get("domain", "")]
        names = {c.get("name") for c in target}
        print(f"X 관련 쿠키 {len(target)}개 (auth_token={'auth_token' in names}, ct0={'ct0' in names})")
        if "auth_token" not in names:
            print("경고: auth_token이 없습니다. 해당 프로필에 x.com 로그인이 맞는지 확인 필요.")
            if not target:
                return 1

        # 7) Netscape cookies.txt 저장
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        lines = ["# Netscape HTTP Cookie File", "# SNS Downloader auto-generated", ""]
        for c in target:
            dom = c.get("domain", "")
            flag = "TRUE" if dom.startswith(".") else "FALSE"
            path = c.get("path") or "/"
            secure = "TRUE" if c.get("secure") else "FALSE"
            exp = int(c.get("expires") or 0)
            if exp < 0:
                exp = 0
            lines.append("\t".join([dom, flag, path, secure, str(exp), c.get("name", ""), c.get("value", "")]))
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print("저장 완료 →", OUT)
        print("이제 다운로더에서 트위터 링크를 붙여넣으면 받아집니다. (크롬 다시 열어도 됨)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
