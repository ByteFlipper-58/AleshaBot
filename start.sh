#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

VENV_DIR="venv"

echo "Checking for Python virtual environment..."

# Check for python3 first, then python
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo "ERROR: Python not found. Please install Python 3."
        exit 1
    fi
fi
echo "Using Python command: $PYTHON_CMD"


if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Creating one..."
    $PYTHON_CMD -m venv $VENV_DIR
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        exit 1
    fi
    echo "Virtual environment created."
else
    echo "Virtual environment found."
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Installing/Updating dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi

echo "Starting AleshaBot..."
# Run bot.py directly from the current directory
$PYTHON_CMD bot.py

echo "Bot stopped. Deactivating virtual environment..."
deactivate

echo "Done."
exit 0
