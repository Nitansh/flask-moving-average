#!/bin/bash

echo "Starting Flask Backend Servers..."

# Activate the virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Virtual environment activated."
elif [ -f "env/bin/activate" ]; then
    source env/bin/activate
    echo "Virtual environment activated."
else
    echo "Virtual environment not found, proceeding without it."
fi

# Run python instances in background
for port in 5000 5001 5002 5003 5004 5005 5006; do
    echo "Starting Flask on port $port..."
    python3 app.py $port &
done

echo ""
echo "========================================"
echo "Flask Backend services started!"
echo "========================================"
echo ""
echo "Press Ctrl+C to stop all background services."

wait
