@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

REM 로그인 쿠키 파일 위치 (로컬 PC, 드라이브 동기화 안 됨).
REM X(트위터) 영상·연령제한 유튜브 등 로그인 필요한 영상은 이 파일이 있어야 받아집니다.
REM 브라우저 확장 "Get cookies.txt LOCALLY"로 내보내 아래 경로에 두세요.
set "YTDLP_COOKIES=%USERPROFILE%\Desktop\SNS 다운로드\cookies.txt"

if not exist ".venv\Scripts\python.exe" (
    echo [setup] 가상환경 만드는 중...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ! Python이 설치되어 있는지 확인하세요. 그리고 PATH에 등록되어 있어야 합니다.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo [setup] 의존성 확인 중...
pip install --upgrade pip > nul
pip install -r backend\requirements.txt
if errorlevel 1 (
    echo.
    echo  ! 의존성 설치 실패. 인터넷 연결 확인 후 다시 실행해주세요.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SNS Downloader 실행
echo   브라우저에서 http://localhost:8766 열기
echo   종료하려면 Ctrl+C
echo ========================================
echo.

cd backend
python main.py

endlocal
