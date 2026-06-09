@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

REM ── X(트위터) 로그인 쿠키 한 번 추출 → 바탕화면\SNS 다운로드\cookies.txt ──
REM   크롬에 x.com 로그인만 되어 있으면 됨. 실행하면 크롬이 잠깐 닫혔다 다시 열 수 있음.
REM   프로필은 자동 탐지. 특정 프로필 강제하려면 아래 줄 주석 풀고 이름 지정:
REM set "CHROME_PROFILE=Profile 1"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [1/2] 필요한 모듈 확인 중...
%PY% -m pip install -q websocket-client
if errorlevel 1 (
    echo  ! 모듈 설치 실패. 인터넷 연결을 확인하세요.
    pause
    exit /b 1
)

echo [2/2] X 로그인 쿠키 추출 중...
echo.
%PY% backend\grab_cookies_cdp.py

echo.
echo ========================================
echo  끝났습니다. 위에 "저장 완료"가 떴으면 성공.
echo  이제 다운로더에서 트위터 링크를 붙여넣으면 받아집니다.
echo ========================================
pause
endlocal
