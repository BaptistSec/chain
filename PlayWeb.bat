@echo off
title CHAIN web
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 ChainWeb.py %*
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python ChainWeb.py %*
  goto done
)
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click PlayWeb.bat again.
:done
echo.
pause
