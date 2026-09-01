@echo off
chcp 936 >nul
title CNKI Icon Cache Clear

echo ============================================
echo   CNKI Citation Tool - Icon Cache Clear
echo ============================================
echo.
echo [1/3] Killing old process...
taskkill /f /im "CNKI引文工具.exe" >nul 2>&1
echo        Done.
echo [2/3] Deleting icon cache...
del /f /q "%LOCALAPPDATA%\IconCache.db" >nul 2>&1
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" >nul 2>&1
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" >nul 2>&1
echo        Done.
echo [3/3] Refreshing shell...
ie4uinit.exe -show >nul 2>&1
echo        Done.
echo.
echo ============================================
echo   Complete! Now run CNKI exe to see new icons.
echo   If still showing old:
echo   1) Press F5 in Explorer
echo   2) Unpin / re-pin taskbar
echo   3) Restart PC (most thorough)
echo ============================================
pause
