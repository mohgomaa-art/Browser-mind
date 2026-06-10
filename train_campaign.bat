@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title BrowserMind -- Train on Campaign Data

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo ====================================================================
echo   BrowserMind  --  Train on Explored Sites
echo ====================================================================
echo.

rem ---- configurable knobs -----------------------------------------------
set "EPOCHS=30"
set "MIN_EPISODES=100"
set "MIN_STEPS=3"
set "DATASET=training\dataset_campaign.jsonl"
set "OUTPUT=bc_v2_checkpoint.pt"
set "BENCH_RUNS=3"
set "REGRESSION=0.05"
rem -----------------------------------------------------------------------

echo   Dataset file  : %DATASET%
echo   Checkpoint    : %OUTPUT%
echo   Epochs        : %EPOCHS%
echo   Min episodes  : %MIN_EPISODES%
echo   Min steps/ep  : %MIN_STEPS%
echo   Bench runs    : %BENCH_RUNS%
echo.

rem --- Step 1: show current ledger readiness ----------------------------
echo [1/4] Ledger status
"%PY%" bm.py dataset status
if errorlevel 1 (
    echo [ERROR] Could not read OutcomeLedger.
    pause
    exit /b 1
)
echo.

rem --- Step 2: export success-only dataset, filtered to campaign sites ---
echo [2/4] Collecting explored site list from campaign queue...
if not exist training mkdir training

rem Build --site flags from the campaign queue (only done sites with steps>0)
for /f "delims=" %%F in ('"%PY%" scripts\campaign_site_flags.py') do set "SITE_FLAGS=%%F"
if "%SITE_FLAGS%"=="" (
    echo [WARN] No campaign-done sites found in queue — exporting all ledger records.
) else (
    echo   Filtering to explored sites only.
)

echo [2/4] Exporting dataset  ^(success-only, min-steps=%MIN_STEPS%^)
"%PY%" bm.py dataset export ^
    --output "%DATASET%" ^
    --success-only ^
    --min-steps %MIN_STEPS% ^
    %SITE_FLAGS%
if errorlevel 1 (
    echo [ERROR] Dataset export failed.
    pause
    exit /b 1
)
if not exist "%DATASET%" (
    echo [ERROR] Dataset file not created: %DATASET%
    pause
    exit /b 1
)
for %%A in ("%DATASET%") do (
    echo   Wrote: %%~zA bytes  ^(%%A^)
)
echo.

rem --- Step 3: train + benchmark + regression-gate ----------------------
echo [3/4] Training  ^(this may take several minutes^)
"%PY%" bm.py self-train ^
    --dataset "%DATASET%" ^
    --epochs %EPOCHS% ^
    --min-episodes %MIN_EPISODES% ^
    --output %OUTPUT% ^
    --benchmark ^
    --benchmark-runs %BENCH_RUNS% ^
    --regression-threshold %REGRESSION% ^
    --headless
set "TRAIN_CODE=%errorlevel%"
echo.

rem --- Step 4: result summary -------------------------------------------
echo [4/4] Summary
if %TRAIN_CODE%==0 (
    echo   [OK] Training complete. Checkpoint: %OUTPUT%
    if exist "%OUTPUT%" (
        for %%A in ("%OUTPUT%") do echo   Size: %%~zA bytes
    )
) else (
    echo   [FAIL] self-train exited with code %TRAIN_CODE%
    echo   Check output above for regression or episode-count failures.
)
echo.

"%PY%" bm.py dataset status 2>nul
echo.

echo ====================================================================
echo   Done.  Checkpoint: %OUTPUT%
echo ====================================================================
echo.
pause
