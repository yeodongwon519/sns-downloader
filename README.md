# SNS Downloader

YouTube · X(Twitter) · Instagram 통합 다운로드 사이트. 내 PC에서 돌리고 어디서든 접속.

## 1. 실행

```
run.bat
```

처음 실행하면 가상환경 만들고 의존성 깔아. 두 번째부터는 바로 켜져.
브라우저에서 `http://localhost:8766` 열면 끝.

## 2. 어디서든 접속하기 (Cloudflare Tunnel)

PC를 켜둔 상태에서 핸드폰·노트북에서 접속하고 싶을 때.

### cloudflared 설치

PowerShell에서:
```
winget install --id Cloudflare.cloudflared
```

설치 안 되면 [여기서 직접 받아](https://github.com/cloudflare/cloudflared/releases) `cloudflared.exe`를 PATH 폴더에 넣어.

### 실행

`run.bat` 켜놓은 상태에서 새 창에서:
```
run-tunnel.bat
```

몇 초 후 콘솔에 이런 줄이 떠:
```
INF +--------------------------------------------------------------------+
INF |  Your quick Tunnel has been created! Visit it at:                  |
INF |  https://random-words-xxx.trycloudflare.com                        |
INF +--------------------------------------------------------------------+
```

이 주소로 핸드폰에서도 접속 가능. 주소는 cloudflared 끄면 사라지고 다음번에 다시 켜면 새 주소가 발급돼.

### 고정 주소 (선택)

매번 주소 바뀌는 게 싫으면 Cloudflare 무료 계정 만들고 named tunnel 설정. 가이드:
https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/

## 3. 보안 토큰 (외부 노출 시 강력 추천)

외부에서 접속할 수 있게 만들었으면 토큰 걸어둬. 안 그러면 주소만 알면 누구나 다운로드 시킬 수 있어.

`run.bat` 첫 줄 근처에 추가:
```bat
set DOWNLOADER_TOKEN=네가-정한-긴-문자열-아무거나
```

브라우저에서는 첫 접속 시 토큰을 URL이나 쿠키로 줘야 함:
```
https://xxx.trycloudflare.com/?token=네가-정한-긴-문자열-아무거나
```

또는 콘솔에서 한 번:
```js
document.cookie = "token=네가-정한-긴-문자열-아무거나; path=/; max-age=2592000"
```

## 4. 다운로드 위치

파일은 vault(구글드라이브)가 아니라 **로컬 PC 바탕화면**에 저장돼:

```
바탕화면/SNS 다운로드/
├── youtube/
├── twitter/
└── instagram/<계정명>/
```

다른 위치로 바꾸려면 `DOWNLOAD_DIR` 환경변수를 지정하면 돼.
브라우저에서도 다운로드 링크로 받을 수 있고, 본인 PC라면 그냥 폴더 열어보면 돼.

## 5. Instagram 로그인

- 본인 인스타 ID/비번이 필요해 (대상 계정이 비공개면 본인이 팔로우하고 있어야 함)
- 첫 로그인 후 `sessions/<id>.json`에 세션 저장 → 다음부턴 자동 로그인
- 2FA 켜져 있으면 2FA 코드 입력칸에 입력
- 비밀번호는 네 PC 외부로 안 나가 (사이트 코드는 너 혼자 쓰는 거)

## 6. 종료

- 서버 종료: `run.bat` 창에서 Ctrl+C
- 터널 종료: `run-tunnel.bat` 창에서 Ctrl+C

## 7. 폴더 구조

```
SNS 다운로더/
├── backend/
│   ├── main.py              FastAPI 서버
│   ├── requirements.txt
│   ├── make_cookies.py      X(트위터) 쿠키 추출 헬퍼
│   ├── grab_cookies_cdp.py  X 쿠키 추출(CDP 방식) 헬퍼
│   └── downloaders/
│       ├── youtube.py
│       ├── twitter.py
│       ├── instagram.py
│       └── _cookies.py      cookies.txt 자동 탐색
├── frontend/
│   └── index.html           단일 페이지 UI
├── run.bat
├── run-tunnel.bat
├── .gitignore
└── README.md

# 실행 중 생성(=git 제외): .venv/  sessions/(인스타 세션)  그리고 바탕화면의 다운로드 결과물
```
