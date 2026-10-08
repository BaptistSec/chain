@echo off
title CHAIN CH10 run
cd /d "%~dp0"
set CHAIN_LAUNCHER=1
set CHAINARGS=%*
if "%~1"=="" set CHAINARGS=--run 1
mode con: cols=110 lines=50 >nul 2>nul
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 ChainDemo.py %CHAINARGS%
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python ChainDemo.py %CHAINARGS%
  goto done
)
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click Play.bat again.
:done
echo.
pause
