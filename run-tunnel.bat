@echo off
chcp 65001 > nul
setlocal

REM Cloudflare Tunnel quick-launch.
REM cloudflared가 설치되어 있어야 합니다. README 참고.

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo.
    echo  ! cloudflared가 설치되어 있지 않습니다.
    echo    설치: winget install --id Cloudflare.cloudflared
    echo    또는: https://github.com/cloudflare/cloudflared/releases
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Cloudflare Quick Tunnel 시작
echo   몇 초 후 출력되는 https://xxx.trycloudflare.com 주소로
echo   어디서든 접속할 수 있습니다.
echo ========================================
echo.

cloudflared tunnel --url http://localhost:8766

endlocal
