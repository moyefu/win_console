@echo off
chcp 65001 >nul
echo ========================================
echo  Building WinConsole standalone exe
echo ========================================
echo.

REM Install dependencies first
pip install -r requirements.txt

REM Clean previous builds
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Building with PyInstaller (--onefile) ...
echo This will take a while...

pyinstaller --onefile --noconsole ^
  --name WinConsole ^
  --add-data "templates;templates" ^
  --hidden-import pynput.keyboard ^
  --hidden-import pynput.mouse ^
  --hidden-import pynput._util ^
  --hidden-import pynput._util.win32 ^
  --hidden-import psutil ^
  --hidden-import pystray ^
  --hidden-import flask_sock ^
  --hidden-import simple_websocket ^
  --hidden-import wsproto ^
  --noconfirm ^
  app.py

if %errorlevel% equ 0 (
  echo.
  echo ========================================
  echo  Build SUCCESS!
  echo  Exe: dist\WinConsole.exe
  echo  Size:
  for %%f in (dist\WinConsole.exe) do echo  %%~zf bytes
  echo ========================================
  echo.
  echo  Usage:
  echo    dist\WinConsole.exe             启动服务
  echo    dist\WinConsole.exe --install   添加开机自�?  echo    dist\WinConsole.exe --uninstall 移除开机自�?  echo.
  echo  启动后浏览器自动打开，也可手动访问：
  echo    http://127.0.0.1:9081
  echo.
  echo  日志文件�?  echo    %%USERPROFILE%%\.winconsole\winconsole.log
  echo ========================================
) else (
  echo.
  echo  Build FAILED! Check errors above.
)
pause
