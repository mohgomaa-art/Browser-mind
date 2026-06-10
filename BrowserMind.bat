@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title BrowserMind
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

:MAIN_MENU
cls
echo ====================================================================
echo   BrowserMind  -  Autonomous Browser Intelligence
echo ====================================================================
echo.
"%PY%" bm.py status 2^>nul
echo.
echo ====================================================================
echo.
echo   CAMPAIGN
echo   [1]  Run 500-site campaign
echo   [2]  Run worker only (resume existing queue)
echo   [3]  Seed queue (add sites without running)
echo.
echo   MISSION CONTROL
echo   [4]  Show queue
echo   [5]  Add a site to queue
echo   [6]  Intervene (login / captcha / manual step)
echo   [7]  Resume a paused site
echo   [8]  Corpus stats
echo.
echo   STUDIO
echo   [9]  Start sidecar API (:8766)
echo   [10] Open desktop UI
echo   [11] Open web UI (browser)
echo.
echo   TOOLS
echo   [12] Explore a single site
echo   [13] Doctor (pre-flight checks)
echo   [14] Run tests
echo.
echo   MODEL
echo   [15] Train model  (self-train: extract -^> train -^> benchmark -^> deploy)
echo   [16] Build dataset (export OutcomeLedger to JSONL)
echo   [17] Run benchmark suite
echo   [18] Replay a workflow template
echo.
echo   [0]  Exit
echo.
set "CHOICE="
set /p CHOICE=  Choice: 
echo.

if "%CHOICE%"=="1"  goto CAMPAIGN
if "%CHOICE%"=="2"  goto WORKER_ONLY
if "%CHOICE%"=="3"  goto SEED_QUEUE
if "%CHOICE%"=="4"  goto SHOW_QUEUE
if "%CHOICE%"=="5"  goto ADD_SITE
if "%CHOICE%"=="6"  goto INTERVENE
if "%CHOICE%"=="7"  goto RESUME_SITE
if "%CHOICE%"=="8"  goto CORPUS
if "%CHOICE%"=="9"  goto SIDECAR
if "%CHOICE%"=="10" goto STUDIO_TAURI
if "%CHOICE%"=="11" goto STUDIO_WEB
if "%CHOICE%"=="12" goto EXPLORE_SITE
if "%CHOICE%"=="13" goto DOCTOR
if "%CHOICE%"=="14" goto RUN_TESTS
if "%CHOICE%"=="15" goto TRAIN_MODEL
if "%CHOICE%"=="16" goto BUILD_DATASET
if "%CHOICE%"=="17" goto RUN_BENCHMARK
if "%CHOICE%"=="18" goto REPLAY_TEMPLATE
if "%CHOICE%"=="0"  exit /b 0
goto MAIN_MENU


rem ====================================================================
rem  [1] CAMPAIGN
rem ====================================================================
:CAMPAIGN
cls
echo ====================================================================
echo   500-Site Capability Discovery Campaign
echo ====================================================================
echo.
set "CAMPAIGN_LIMIT=500"
set "MAX_DIFFICULTY=3"
set "BUDGET_PER_SITE=200"
set "PERSONA=validator"
set "DELAY_BETWEEN_SITES=3"
set "STATS_EVERY=10"
set "HEADLESS_FLAG="

echo   CAMPAIGN_LIMIT  : %CAMPAIGN_LIMIT%
echo   MAX_DIFFICULTY  : %MAX_DIFFICULTY%
echo   BUDGET_PER_SITE : %BUDGET_PER_SITE% steps
echo   PERSONA         : %PERSONA%
echo.
echo   Ctrl+C to stop. Queue is persistent - restart to resume.
echo.
set "READY="
set /p READY=  Press ENTER to begin (or type n to cancel): 
if /i "%READY%"=="n" goto MAIN_MENU

echo.
echo   Browser mode:
echo     [H] Headless  -- no window, faster, for unattended runs
echo     [V] Visible   -- browser visible, required for manual login
echo.
set "BMODE="
set /p BMODE=  Choose [H/V] (default=V): 
if /i "%BMODE%"=="H" set "HEADLESS_FLAG=--headless"

echo.
echo [1/3] Running pre-flight checks...
"%PY%" bm.py doctor
if errorlevel 1 (
    echo.
    echo [ERROR] Doctor check failed. Fix issues above before running.
    pause
    goto MAIN_MENU
)

echo.
echo [2/3] Seeding queue with up to %CAMPAIGN_LIMIT% sites...
"%PY%" bm.py site add-campaign --limit %CAMPAIGN_LIMIT% --max-difficulty %MAX_DIFFICULTY% --budget %BUDGET_PER_SITE% --persona %PERSONA%
echo.
"%PY%" bm.py mission status
echo.

echo [3/3] Starting sidecar in background...
start "BrowserMind Sidecar" /min cmd /c "%PY% bm.py sidecar start"
timeout /t 2 /nobreak >nul

echo.
echo ====================================================================
echo   Campaign running -- Ctrl+C to stop
echo   Sidecar : http://127.0.0.1:8766
echo ====================================================================
echo.

set "RESTART_COUNT=0"

:CAMPAIGN_LOOP
set /a RESTART_COUNT+=1
echo [Run #!RESTART_COUNT!]  %DATE% %TIME%
echo.
"%PY%" bm.py mission run %HEADLESS_FLAG% --delay %DELAY_BETWEEN_SITES%
set "EXIT_CODE=%errorlevel%"

if %EXIT_CODE%==0 goto CAMPAIGN_END

echo.
echo [RESTART] Worker exited (code %EXIT_CODE%) -- restarting in 5s...

set /a "MOD=RESTART_COUNT %% STATS_EVERY"
if !MOD!==0 (
    echo.
    "%PY%" bm.py corpus stats
    echo.
    "%PY%" bm.py mission ls --status paused 2>nul
    echo.
)

timeout /t 5 /nobreak >nul
goto CAMPAIGN_LOOP

:CAMPAIGN_END
echo.
echo ====================================================================
echo   Campaign complete after !RESTART_COUNT! run(s)
echo ====================================================================
echo.
"%PY%" bm.py corpus stats
echo.
"%PY%" bm.py mission ls --status paused 2>nul
echo.
if not exist exports mkdir exports
set "CSVOUT=exports\campaign_500_results.csv"
"%PY%" bm.py corpus export --output "%CSVOUT%" 2>nul
if exist "%CSVOUT%" echo [OK] Results exported to %CSVOUT%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [2] WORKER ONLY
rem ====================================================================
:WORKER_ONLY
cls
echo ====================================================================
echo   Mission Worker
echo ====================================================================
echo.
set "HEADLESS_FLAG="
echo   Browser mode:  [H] Headless    [V] Visible (default=V)
echo.
set "BMODE="
set /p BMODE=  Choose [H/V]: 
if /i "%BMODE%"=="H" set "HEADLESS_FLAG=--headless"

set "HOURS="
set /p HOURS=  Run for how many hours? (blank = unlimited): 
set "HOURS_FLAG="
if not "%HOURS%"=="" set "HOURS_FLAG=--hours %HOURS%"

echo.
"%PY%" bm.py mission status
echo.
"%PY%" bm.py mission run %HEADLESS_FLAG% %HOURS_FLAG%
pause
goto MAIN_MENU


rem ====================================================================
rem  [3] SEED QUEUE
rem ====================================================================
:SEED_QUEUE
cls
echo ====================================================================
echo   Seed Mission Queue
echo ====================================================================
echo.
set "SLIMIT=500"
set "SDIFFICULTY=3"
set "SBUDGET=200"
set /p SLIMIT=  Max sites (default 500): 
set /p SDIFFICULTY=  Max difficulty 1-5 (default 3): 
set /p SBUDGET=  Budget per site (default 200): 
echo.
"%PY%" bm.py site add-campaign --limit %SLIMIT% --max-difficulty %SDIFFICULTY% --budget %SBUDGET% --persona validator
echo.
"%PY%" bm.py mission status
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [4] SHOW QUEUE
rem ====================================================================
:SHOW_QUEUE
cls
echo ====================================================================
echo   Mission Queue
echo ====================================================================
echo.
echo   [1] All    [2] Pending    [3] Paused    [4] Done    [5] Failed
echo.
set "QFILTER="
set /p QFILTER=  Filter (1-5, blank=all): 
if "%QFILTER%"=="2" "%PY%" bm.py mission ls --status pending
if "%QFILTER%"=="3" "%PY%" bm.py mission ls --status paused
if "%QFILTER%"=="4" "%PY%" bm.py mission ls --status done
if "%QFILTER%"=="5" "%PY%" bm.py mission ls --status failed
if "%QFILTER%"==""  "%PY%" bm.py mission ls
if "%QFILTER%"=="1" "%PY%" bm.py mission ls
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [5] ADD SITE
rem ====================================================================
:ADD_SITE
cls
echo ====================================================================
echo   Add Site to Queue
echo ====================================================================
echo.
set "ASITE="
set /p ASITE=  Site key (e.g. github, reddit): 
if "%ASITE%"=="" goto MAIN_MENU
set "ABUDGET=200"
set /p ABUDGET=  Budget (default 200): 
echo.
"%PY%" bm.py mission add %ASITE% --budget %ABUDGET%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [6] INTERVENE
rem ====================================================================
:INTERVENE
cls
echo ====================================================================
echo   Human Intervention (login / captcha / MFA)
echo ====================================================================
echo.
echo   Opens a visible browser so you can complete the manual step.
echo   Session is saved automatically when you press ENTER.
echo.
"%PY%" bm.py mission ls --status paused 2>nul
echo.
set "ISITE="
set /p ISITE=  Site key to intervene on: 
if "%ISITE%"=="" goto MAIN_MENU
set "IPERSONA=validator"
set /p IPERSONA=  Persona (default=validator): 
echo.
"%PY%" bm.py mission intervene %ISITE% --persona %IPERSONA%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [7] RESUME PAUSED SITE
rem ====================================================================
:RESUME_SITE
cls
echo ====================================================================
echo   Resume Paused Site
echo ====================================================================
echo.
"%PY%" bm.py mission ls --status paused 2>nul
echo.
set "RSITE="
set /p RSITE=  Site key to resume: 
if "%RSITE%"=="" goto MAIN_MENU
"%PY%" bm.py mission resume %RSITE%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [8] CORPUS STATS
rem ====================================================================
:CORPUS
cls
echo ====================================================================
echo   Corpus Statistics
echo ====================================================================
echo.
"%PY%" bm.py corpus stats
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [9] SIDECAR
rem ====================================================================
:SIDECAR
cls
echo ====================================================================
echo   Sidecar API  (:8766)
echo ====================================================================
echo.
echo   Studio UI connects to http://127.0.0.1:8766
echo   Press Ctrl+C to stop.
echo.
pause
"%PY%" bm.py sidecar start
pause
goto MAIN_MENU


rem ====================================================================
rem  [10] STUDIO TAURI
rem ====================================================================
:STUDIO_TAURI
cls
echo ====================================================================
echo   Studio UI (desktop)
echo ====================================================================
echo.
echo   Requires: sidecar running at :8766, Node.js + Rust + Tauri CLI
echo.
cd /d "%~dp0browsermind_ui_tauri"
if not exist node_modules (
    echo Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        cd /d "%~dp0"
        pause
        goto MAIN_MENU
    )
)
call npm run tauri:dev
cd /d "%~dp0"
pause
goto MAIN_MENU


rem ====================================================================
rem  [11] STUDIO WEB
rem ====================================================================
:STUDIO_WEB
cls
echo ====================================================================
echo   Studio UI (browser at http://localhost:5173)
echo ====================================================================
echo.
cd /d "%~dp0browsermind_ui_tauri"
if not exist node_modules (
    echo Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        cd /d "%~dp0"
        pause
        goto MAIN_MENU
    )
)
call npm run dev
cd /d "%~dp0"
pause
goto MAIN_MENU


rem ====================================================================
rem  [12] EXPLORE SINGLE SITE
rem ====================================================================
:EXPLORE_SITE
cls
echo ====================================================================
echo   Explore a Single Site
echo ====================================================================
echo.
set "ESITE="
set /p ESITE=  Site key: 
if "%ESITE%"=="" goto MAIN_MENU
set "EBUDGET=100"
set /p EBUDGET=  Budget / max steps (default 100): 
echo   Browser: [H] Headless    [V] Visible (default=V)
set "EMODE="
set /p EMODE=  Choose [H/V]: 
set "EHEADLESS="
if /i "%EMODE%"=="H" set "EHEADLESS=--headless"
echo.
"%PY%" bm.py explore --site %ESITE% --budget %EBUDGET% %EHEADLESS%
pause
goto MAIN_MENU


rem ====================================================================
rem  [13] DOCTOR
rem ====================================================================
:DOCTOR
cls
echo ====================================================================
echo   Doctor -- Pre-flight Checks
echo ====================================================================
echo.
"%PY%" bm.py doctor
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [14] RUN TESTS
rem ====================================================================
:RUN_TESTS
cls
echo ====================================================================
echo   Test Suite
echo ====================================================================
echo.
"%PY%" -m pytest browsermind_core\tests\ -v --tb=short -q
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [15] TRAIN MODEL
rem ====================================================================
:TRAIN_MODEL
cls
echo ====================================================================
echo   Train Model  (self-train pipeline)
echo ====================================================================
echo.
echo   Pipeline: OutcomeLedger -^> JSONL dataset -^> BC training -^> benchmark -^> deploy
echo.
"%PY%" -m browsermind_core.console.cli dataset status
echo.
set "TEPOCHS=30"
set "TMIN=100"
set "TOUT=bc_v2_checkpoint.pt"
set "THEADLESS="
set /p TEPOCHS=  Epochs          (default 30):
set /p TMIN=     Min episodes    (default 100):
set /p TOUT=     Output file     (default bc_v2_checkpoint.pt):
echo.
echo   Run benchmark after training? [Y/N] (default=Y)
set "TBENCH=Y"
set /p TBENCH=  Benchmark [Y/N]:
set "TBENCH_FLAG=--benchmark"
if /i "%TBENCH%"=="N" set "TBENCH_FLAG=--no-benchmark"
echo.
echo   Browser: [H] Headless    [V] Visible (default=H)
set "TMODE=H"
set /p TMODE=  Choose [H/V]:
if /i "%TMODE%"=="H" set "THEADLESS=--headless"
echo.
echo   Starting self-train...
echo.
"%PY%" -m browsermind_core.console.cli self-train ^
    --epochs %TEPOCHS% ^
    --min-episodes %TMIN% ^
    --output %TOUT% ^
    %TBENCH_FLAG% %THEADLESS%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [16] BUILD DATASET
rem ====================================================================
:BUILD_DATASET
cls
echo ====================================================================
echo   Build Training Dataset
echo ====================================================================
echo.
echo   Flattens the OutcomeLedger into a BC-ready JSONL file.
echo.
"%PY%" -m browsermind_core.console.cli dataset status
echo.
set "DOUT=training\dataset_autotrain.jsonl"
set "DMIN=0"
set "DALL="
set /p DOUT=  Output file   (default training\dataset_autotrain.jsonl):
set /p DMIN=  Min steps     (default 0 = keep all):
echo.
echo   Include failed steps? [Y/N] (default=N, success-only)
set "DMODE=N"
set /p DMODE=  All steps [Y/N]:
set "DALL_FLAG=--success-only"
if /i "%DMODE%"=="Y" set "DALL_FLAG=--all"
echo.
"%PY%" -m browsermind_core.console.cli dataset export ^
    --output "%DOUT%" ^
    --min-steps %DMIN% ^
    %DALL_FLAG%
echo.
if exist "%DOUT%" (
    echo [OK] Dataset written to %DOUT%
    for %%A in ("%DOUT%") do echo     Size: %%~zA bytes
)
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [17] RUN BENCHMARK
rem ====================================================================
:RUN_BENCHMARK
cls
echo ====================================================================
echo   Benchmark Suite
echo ====================================================================
echo.
set "BRUNS=5"
set "BHEADLESS=--headless"
set "BCOMPARE="
set /p BRUNS=  Runs per template (default 5):
echo.
echo   Browser: [H] Headless    [V] Visible (default=H)
set "BMODE=H"
set /p BMODE=  Choose [H/V]:
if /i "%BMODE%"=="V" set "BHEADLESS="
echo.
echo   Compare against a prior run? (paste JSON path or leave blank)
set "BPRIOR="
set /p BPRIOR=  Prior benchmark JSON:
if not "%BPRIOR%"=="" set "BCOMPARE=--compare %BPRIOR%"
echo.
"%PY%" -m browsermind_core.console.cli benchmark run ^
    --runs %BRUNS% ^
    %BHEADLESS% %BCOMPARE%
echo.
pause
goto MAIN_MENU


rem ====================================================================
rem  [18] REPLAY TEMPLATE
rem ====================================================================
:REPLAY_TEMPLATE
cls
echo ====================================================================
echo   Replay a Workflow Template
echo ====================================================================
echo.
"%PY%" -m browsermind_core.console.cli workflow ls 2>nul | head -20 2>nul
echo.
set "RTEMPLATE="
set "RENV=huggingface"
set "RPERSONA=validator"
set "RURL="
set "RHEADLESS="
set "RSKIP="
set /p RTEMPLATE=  Template name (required):
if "%RTEMPLATE%"=="" goto MAIN_MENU
set /p RENV=       Environment   (default huggingface):
set /p RPERSONA=   Persona       (default validator):
echo.
echo   Override start URL? (leave blank to use registry default)
set /p RURL=  Start URL:
set "RURL_FLAG="
if not "%RURL%"=="" set "RURL_FLAG=--url %RURL%"
echo.
echo   Browser: [H] Headless    [V] Visible (default=V)
set "RMODE=V"
set /p RMODE=  Choose [H/V]:
if /i "%RMODE%"=="H" set "RHEADLESS=--headless"
echo.
echo   Skip failures and continue? [Y/N] (default=N)
set "RSKIPMODE=N"
set /p RSKIPMODE=  Skip failures [Y/N]:
if /i "%RSKIPMODE%"=="Y" set "RSKIP=--skip-failures"
echo.
"%PY%" -m browsermind_core.console.cli replay start %RTEMPLATE% ^
    --env %RENV% ^
    --persona %RPERSONA% ^
    %RURL_FLAG% %RHEADLESS% %RSKIP%
echo.
pause
goto MAIN_MENU