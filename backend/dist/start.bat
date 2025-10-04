@echo off
title Email Verifier - Free Edition
color 0A

set ROOT=%~dp0..
set INPUT=%ROOT%\sample_files
set OUTPUT=%ROOT%\output

echo ===========================================
echo        Email Verifier - Free Edition
echo ===========================================
echo.
echo Input Folder : %INPUT%
echo Output Folder: %OUTPUT%
echo.
echo Please wait... verifying emails.
echo.

email-verifier.exe --input "%INPUT%" --output "%OUTPUT%"

echo.
echo ✅ Done! Results saved in the "output" folder.
echo.
pause
