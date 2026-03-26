#!/bin/bash

echo "Starting Flask Backend Servers..."

# Determine python executable
PYTHON_CMD="python3"
if [ -f "venv/bin/python3" ]; then
    PYTHON_CMD="venv/bin/python3"
    echo "Using virtual environment (venv)."
elif [ -f "env/bin/python3" ]; then
    PYTHON_CMD="env/bin/python3"
    echo "Using virtual environment (env)."
else
    echo "Virtual environment not found, using global python3."
fi

# Run python instances in background
for port in 5000 5001 5002 5003 5004 5005 5006; do
    echo "Starting Flask on port $port..."
    $PYTHON_CMD app.py $port &
done

echo ""
echo "========================================"
echo "Flask Backend services started!"
echo "========================================"
echo ""
echo "Press Ctrl+C to stop all background services."

wait
