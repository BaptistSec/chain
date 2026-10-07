@echo off
title CHAIN test board
cd /d "%~dp0"
set CHAIN_LAUNCHER=1
mode con: cols=110 lines=50 >nul 2>nul
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 ChainDemo.py %*
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python ChainDemo.py %*
  goto done
)
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click Play.bat again.
:done
echo.
pause
