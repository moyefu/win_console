@echo off
chcp 65001 >nul
echo ========================================
echo  Building WinConsole Server
echo ========================================
echo.

REM Install dependencies
pip install -e ".[server]"

REM Clean previous builds
if exist dist\server rmdir /s /q dist\server
if exist build\server rmdir /s /q build\server

echo Building with PyInstaller (--onefile) ...
echo This will take a while...

pyinstaller --onefile --noconsole ^
  --name WinConsoleServer ^
  --add-data "templates;templates" ^
  --add-data "common;common" ^
  --hidden-import flask ^
  --hidden-import flask_sock ^
  --hidden-import simple_websocket ^
  --hidden-import wsproto ^
  --hidden-import psutil ^
  --hidden-import pystray ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import PIL.ImageGrab ^
  --hidden-import cryptography ^
  --hidden-import websockets ^
  --noconfirm ^
  --distpath dist\server ^
  --workpath build\server ^
  server\main.py

if %errorlevel% equ 0 (
  echo.
  echo ========================================
  echo  Build SUCCESS!
  echo  Exe: dist\server\WinConsoleServer.exe
  echo ========================================
) else (
  echo.
  echo  Build FAILED! Check errors above.
)
pause
