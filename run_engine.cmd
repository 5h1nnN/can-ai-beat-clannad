@echo off
rem ============================================================
rem  CLANNAD MCP - engine launcher
rem
rem  Put this file next to siglus_engine.exe and edit GAME_DIR,
rem  then run it (double click, or from a terminal).
rem ============================================================
setlocal

rem [1] Your CLANNAD install: the folder that contains Scene.pck,
rem     dat\, g00\, mov\ and savedata_zh\.
set "GAME_DIR=E:\SteamLibrary\steamapps\common\CLANNAD"

rem [2] Port file shared with the MCP server. BOTH sides must use the
rem     same path: set the same CLANNAD_BRIDGE_PORT_FILE in your MCP
rem     host config (see README.md).
set "CLANNAD_BRIDGE_PORT_FILE=%TEMP%\clannad_bridge.port"

rem [3] Chinese text / engine options (see README.md for the full list).
set "SIGLUS_LANGUAGE=ZH"
rem Wall-clock budget of one fast-forward (ms). Keep it well below the
rem MCP client's own timeout (the client default is 45 s).
set "CLANNAD_SKIP_BUDGET_MS=40000"

if not exist "%~dp0siglus_engine.exe" (
  echo [ERROR] siglus_engine.exe not found next to this script.
  echo         Put the launcher in the folder with the engine, or edit the path below.
  pause
  exit /b 1
)
if not exist "%GAME_DIR%\Scene.pck" (
  echo [ERROR] GAME_DIR does not look like a CLANNAD install:
  echo         %GAME_DIR%
  echo         Edit GAME_DIR at the top of this file.
  pause
  exit /b 1
)

echo [engine] project : %GAME_DIR%
echo [engine] portfile: %CLANNAD_BRIDGE_PORT_FILE%
echo [engine] starting ... (the game window opens; enter Ctrl to fast-forward)
"%~dp0siglus_engine.exe" --project-dir "%GAME_DIR%" --bridge --auto-start %*

endlocal
