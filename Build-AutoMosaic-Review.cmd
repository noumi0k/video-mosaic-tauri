@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

set "MODE=%~1"
if /I "%MODE%"=="" set "MODE=portable"

if /I "%MODE%"=="portable" goto run_portable
if /I "%MODE%"=="zip" goto run_zip
if /I "%MODE%"=="help" goto show_help

echo Unknown mode: %MODE%
echo.
goto show_help

:run_portable
echo Building AutoMosaic review folder...
call npm.cmd --workspace apps/desktop run review:portable
if errorlevel 1 goto failed

echo.
echo AutoMosaic-Review has been refreshed:
echo   %SCRIPT_DIR%AutoMosaic-Review
goto done

:run_zip
echo Building AutoMosaic review folder and zip...
call npm.cmd --workspace apps/desktop run review:zip
if errorlevel 1 goto failed

echo.
echo AutoMosaic-Review has been refreshed:
echo   %SCRIPT_DIR%AutoMosaic-Review
echo Review zip has been refreshed:
echo   %SCRIPT_DIR%AutoMosaic-Review-Windows.zip
goto done

:show_help
echo Usage:
echo   Build-AutoMosaic-Review.cmd
echo   Build-AutoMosaic-Review.cmd portable
echo   Build-AutoMosaic-Review.cmd zip
echo.
echo portable: refreshes the AutoMosaic-Review folder for local review
echo zip     : also refreshes AutoMosaic-Review-Windows.zip for handoff
exit /b 1

:failed
echo.
echo Review package build failed.
echo Fix the error above and run this file again.
popd >nul
exit /b 1

:done
popd >nul
exit /b 0
