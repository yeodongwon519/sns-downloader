"""Chrome을 임시 프로필 사본으로 잠깐 띄워서, X 로그인 쿠키를 CDP로 받아 cookies.txt 저장.

App-Bound Encryption(최신 Chrome)을 우회한다: 복호화는 Chrome 자신이 수행하고,
우리는 DevTools Protocol(Network.getAllCookies)로 이미 복호화된 쿠키를 받는다.
관리자 권한 불필요. 모든 처리는 로컬 PC 안에서만.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
SRC_PROFILE = os.environ.get("CHROME_PROFILE", "Profile 3")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "SNS 다운로드", "cookies.txt")
PORT = 9777


def free_port_ok() -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> int:
    if not os.path.exists(CHROME):
        print("chrome.exe를 찾을 수 없습니다:", CHROME)
        return 1

    # 1) 잠금 해제를 위해 Chrome 종료
    subprocess.run(["taskkill", "/im", "chrome.exe", "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # 2) 임시 user-data-dir에 필요한 파일만 복사 (Local State = ABE 키, 해당 프로필 쿠키)
    tmp = tempfile.mkdtemp(prefix="snsdl_chrome_")
    try:
        shutil.copy2(os.path.join(BASE, "Local State"), os.path.join(tmp, "Local State"))
        netdir = os.path.join(tmp, "Default", "Network")
        os.makedirs(netdir, exist_ok=True)
        src_cookies = os.path.join(BASE, SRC_PROFILE, "Network", "Cookies")
        if not os.path.exists(src_cookies):
            print("쿠키 DB가 없습니다:", src_cookies)
            return 1
        shutil.copy2(src_cookies, os.path.join(netdir, "Cookies"))

        # 3) 임시 프로필로 Chrome 기동 (원래 Chrome과 별개 인스턴스) + 원격 디버깅
        args = [
            CHROME,
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

        # 4) DevTools 엔드포인트 대기
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

        # 5) Network.getAllCookies 호출 (복호화된 전체 쿠키 반환)
        import websocket
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
            print("경고: auth_token이 없습니다. Profile 3에 x.com 로그인이 맞는지 확인 필요.")
            if not target:
                return 1

        # 6) Netscape cookies.txt 저장
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
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
