@echo off
chcp 65001 >nul
echo ========================================
echo   Building WinConsole Client
echo ========================================
echo.

REM Install dependencies
pip install -r client\requirements.txt

REM Clean previous builds
if exist dist\client rmdir /s /q dist\client
if exist build\client rmdir /s /q build\client

echo Using PyInstaller (--onefile --noconsole)...
echo   --noconsole 模式：正常客户端运行时**完全静默**（无 cmd 窗口）
echo   install/test/uninstall 命令会在 main.py 顶部自动 AllocConsole 显示输出
echo This will take a while...

pyinstaller --onefile --noconsole ^
  --name WinConsoleClient ^
  --add-data "common;common" ^
  --hidden-import websockets ^
  --hidden-import psutil ^
  --hidden-import pyautogui ^
  --hidden-import pynput ^
  --hidden-import pynput.keyboard ^
  --hidden-import pynput.mouse ^
  --hidden-import pynput._util ^
  --hidden-import pynput._util.win32 ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import PIL.ImageGrab ^
  --hidden-import cryptography ^
  --noconfirm ^
  --distpath dist\client ^
  --workpath build\client ^
  client\main.py

if %errorlevel% equ 0 (
  echo.
  echo ========================================
  echo  Build SUCCESS!
  echo  Exe: dist\client\WinConsoleClient.exe
  echo ========================================
) else (
  echo.
  echo  Build FAILED! Check errors above.
)
pause
