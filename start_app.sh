#!/bin/bash

echo "========================================"
echo " Starting Stock Analysis Application..."
echo "========================================"
echo ""

BASE_DIR="$(pwd)/moving-average"
FLASK_DIR="$BASE_DIR/flask-moving-average"
NODE_DIR="$BASE_DIR/movingAverage"
CLIENT_DIR="$NODE_DIR/client"

# Activate virtual environment
echo "Activating Python virtual environment..."
source "$FLASK_DIR/venv/bin/activate"

echo "Starting Flask Backend Servers..."

cd "$FLASK_DIR" || exit

python app.py 5000 &
python app.py 5001 &
python app.py 5002 &
python app.py 5003 &
python app.py 5004 &
python app.py 5005 &
python app.py 5006 &

sleep 2

echo "Starting Node.js Backend Server..."
cd "$NODE_DIR" || exit
npm start &

sleep 3

echo "Starting React Frontend Dev Server..."
cd "$CLIENT_DIR" || exit
npm run dev -- --host 0.0.0.0 &

sleep 2

PI_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "========================================"
echo " All services started!"
echo "========================================"
echo ""
echo "React Frontend:  http://$PI_IP:5173"
echo "Node Backend:    http://$PI_IP:3000"
echo "Flask Backends:  http://$PI_IP:5000-5006"
echo ""
