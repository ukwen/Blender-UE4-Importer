@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run with x64 MinGW-w64 GCC and G++ on PATH (e.g. MSYS2 UCRT64 toolchain).
rem Build from separately acquired pinned sources. Never package their binaries in the addon.
if "%~3"=="" goto usage
set "OOZ=%~f1"
set "B3=%~f2"
set "OUTPUT=%~f3"
if not exist "%OOZ%\ooz.h" goto usage
if not exist "%B3%\blake3.h" goto usage
where gcc.exe >nul 2>&1 || goto missing
where g++.exe >nul 2>&1 || goto missing
if exist "%OUTPUT%" (echo Output already exists; choose a new path.& exit /b 2)
set "WORK=%TEMP%\ue-editor-decoder-%RANDOM%-%RANDOM%"
mkdir "%WORK%" || exit /b 2
for %%N in (blake3 blake3_dispatch blake3_portable) do (
    gcc.exe -O2 -DBLAKE3_NO_SSE2 -DBLAKE3_NO_SSE41 -DBLAKE3_NO_AVX2 -DBLAKE3_NO_AVX512 -DBLAKE3_USE_NEON=0 -I"%B3%" -c "%B3%\%%N.c" -o "%WORK%\%%N.o" || goto failed
)
g++.exe -O2 -msse4.1 -static -I"%OOZ%" -I"%B3%" "%~dp0editor_payload_decoder.cpp" "%OOZ%\kraken.cpp" "%OOZ%\bitknit.cpp" "%OOZ%\lzna.cpp" "%WORK%\blake3.o" "%WORK%\blake3_dispatch.o" "%WORK%\blake3_portable.o" -o "%WORK%\decoder.exe" || goto failed
move /y "%WORK%\decoder.exe" "%OUTPUT%" >nul || goto failed
rmdir /s /q "%WORK%"
echo Decoder built: "%OUTPUT%"
exit /b 0
:failed
rmdir /s /q "%WORK%"
echo Decoder build failed.
exit /b 1
:missing
echo Install x64 MinGW-w64 GCC and G++ and add its bin directory to PATH.
exit /b 2
:usage
echo Usage: %~nx0 PYOOZ_DIR BLAKE3_C_DIR OUTPUT_EXE
exit /b 2
