@echo off
set VENV_DIR=venv

echo Checking for Python virtual environment...

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one...
    python -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment. Make sure Python is installed and in PATH.
        pause
        exit /b %errorlevel%
    )
    echo Virtual environment created.
) else (
    echo Virtual environment found.
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo Installing/Updating dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo Starting AleshaBot...
REM Run bot.py directly from the current directory
python bot.py

echo Bot stopped. Deactivating virtual environment...
call "%VENV_DIR%\Scripts\deactivate.bat"

echo Done.
pause
