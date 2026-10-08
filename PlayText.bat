@echo off
title CHAIN CH14 single board (text mode)
cd /d "%~dp0"
set CHAIN_LAUNCHER=1
mode con: cols=110 lines=50 >nul 2>nul
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 ChainDemo.py --text
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python ChainDemo.py --text
  goto done
)
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click PlayText.bat again.
:done
echo.
pause
