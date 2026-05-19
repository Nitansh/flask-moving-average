#!/bin/bash
# Stock Analysis App - Heartbeat & Auto-Recovery Script
# Runs a health check on all services and restarts them if they fail or give a bad response.

# Auto-detect root directory based on where this script is located
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLASK_DIR="$ROOT_DIR/flask-moving-average"
LOG_DIR="/tmp"
# Fallback for environment variables (used by Render to route traffic to this node)
: "${RENDER_BACKEND_URL:=https://movingaverage-sh7s.onrender.com}"
: "${HEARTBEAT_SECRET:=pi-heartbeat-2024}"

# Cleanup zombie processes if they exist but aren't responding
# sudo fuser -k 8081/tcp 4001/tcp 2>/dev/null
# sudo pkill -9 -f service_manager.py 2>/dev/null
# sudo pkill -9 -f local_balancer.js 2>/dev/null
sleep 2 # Allow OS to release sockets

# Auto-install cron jobs
if [ "$1" == "--install-cron" ]; then
    SCRIPT_PATH=$(readlink -f "$0")
    # Ensure script is executable
    chmod +x "$SCRIPT_PATH"
    
    # Remove existing entries for this script and add new ones
    CRON_CMD_1="*/5 9-14 * * 1-5 $SCRIPT_PATH >> /tmp/heartbeat_cron.log 2>&1"
    CRON_CMD_2="0,5,10,15,20,25,30 15 * * 1-5 $SCRIPT_PATH >> /tmp/heartbeat_cron.log 2>&1"
    BOOT_CMD="@reboot sleep 30 && $SCRIPT_PATH >> /tmp/heartbeat_cron.log 2>&1"
    
    (crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH"; echo "$CRON_CMD_1"; echo "$CRON_CMD_2"; echo "$BOOT_CMD") | crontab -
    
    echo "✅ Successfully installed cron jobs:"
    echo "  - Runs every 5 mins from 09:00 to 14:55 on Mon-Fri (*/5 9-14 * * 1-5)"
    echo "  - Runs every 5 mins from 15:00 to 15:30 on Mon-Fri (0,5,10,15,20,25,30 15 * * 1-5)"
    echo "  - Runs on system bootup (@reboot)"
    exit 0
fi
# =====================================================================
# END-TO-END SETUP & DEPENDENCIES
# =====================================================================
echo "Checking system requirements..."

# Determine package manager if running on Linux
if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="sudo apt-get install -y"
    SUDO_CMD="sudo"
elif command -v yum >/dev/null 2>&1; then
    PKG_MGR="sudo yum install -y"
    SUDO_CMD="sudo"
else
    PKG_MGR=""
    SUDO_CMD=""
fi

# 1. Install Git
if ! command -v git >/dev/null 2>&1; then
    echo "Installing Git..."
    if [ -n "$PKG_MGR" ]; then
        $SUDO_CMD apt-get update -y 2>/dev/null || true
        $PKG_MGR git
    else
        echo "Please install Git manually."
    fi
fi

# 2. Install Python & Virtualenv
if ! command -v python3 >/dev/null 2>&1; then
    echo "Installing Python3..."
    if [ -n "$PKG_MGR" ]; then
        $PKG_MGR python3 python3-pip python3-venv
    else
        echo "Please install Python3 manually."
    fi
fi

# Ensure python3-venv is available (some debian variants separate it)
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    echo "Installing Python3 venv..."
    if [ -n "$PKG_MGR" ]; then
        $PKG_MGR python3-venv
    fi
fi

# 2.5 Install Node.js & NPM
if ! command -v node >/dev/null 2>&1 && [ ! -f "$HOME/.nvm/nvm.sh" ]; then
    echo "Installing Node.js..."
    if command -v apt-get >/dev/null 2>&1; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif command -v yum >/dev/null 2>&1; then
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
        sudo yum install -y nodejs
    else
        echo "Please install Node.js manually."
    fi
fi

# 3. Install Cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Installing Cloudflared..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then
        CF_BIN="cloudflared-linux-amd64"
    elif [ "$ARCH" = "aarch64" ]; then
        CF_BIN="cloudflared-linux-arm64"
    elif [ "$ARCH" = "armv7l" ] || [ "$ARCH" = "armv6l" ]; then
        CF_BIN="cloudflared-linux-arm"
    else
        echo "Unsupported architecture: $ARCH. Please install cloudflared manually."
        CF_BIN=""
    fi
    
    if [ -n "$CF_BIN" ]; then
        curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF_BIN" -o cloudflared
        chmod +x cloudflared
        if command -v sudo >/dev/null 2>&1; then
            sudo mv cloudflared /usr/local/bin/
        else
            mv cloudflared /usr/local/bin/ || echo "Failed to move cloudflared. Run as root."
        fi
    fi
fi

# 3. Clone / Update Repository
if [ ! -d "$FLASK_DIR" ]; then
    echo "Cloning flask-moving-average repository..."
    git clone https://github.com/Nitansh/flask-moving-average.git "$FLASK_DIR"
else
    echo "Repository exists. Pulling latest changes..."
    cd "$FLASK_DIR" && git pull && cd "$ROOT_DIR"
fi

# 4. Setup Virtual Environment and Install Dependencies
echo "Setting up Python virtual environment..."
cd "$FLASK_DIR" || exit

# Create venv if missing or if pip is missing inside it
if [ ! -d "venv" ] || { [ ! -f "venv/bin/pip" ] && [ ! -f "venv/Scripts/pip.exe" ]; }; then
    echo "Creating virtual environment..."
    # Ensure any broken venv is removed
    rm -rf venv
    python3 -m venv venv
    
    # If pip is still somehow missing, install it manually into the venv
    if [ ! -f "venv/bin/pip" ] && [ ! -f "venv/Scripts/pip.exe" ]; then
        echo "Pip not found in venv. Installing pip manually..."
        if [ -f "venv/bin/python3" ]; then
            curl -sS https://bootstrap.pypa.io/get-pip.py | venv/bin/python3
        elif [ -f "venv/Scripts/python.exe" ]; then
            curl -sS https://bootstrap.pypa.io/get-pip.py | venv/Scripts/python.exe
        fi
    fi
fi

# Activate and install requirements using dot (.) instead of source for /bin/sh compatibility
if [ -f "venv/bin/python3" ]; then
    VENV_PYTHON="venv/bin/python3"
    [ -f "venv/bin/activate" ] && . venv/bin/activate
elif [ -f "venv/Scripts/python.exe" ]; then
    # Fallback for Windows
    VENV_PYTHON="venv/Scripts/python.exe"
    [ -f "venv/Scripts/activate" ] && . venv/Scripts/activate
else
    VENV_PYTHON="python3"
fi

echo "Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    # Force Python 3.14 compatibility patches dynamically before pip install
    if command -v sed >/dev/null 2>&1; then
        sed -i 's/Flask>=3.0.0/Flask>=3.1.2/g' requirements.txt || true
        sed -i 's/Werkzeug>=3.0.0/Werkzeug>=3.1.4/g' requirements.txt || true
        sed -i 's/blinker==1.8.2/blinker>=1.9.0/g' requirements.txt || true
    fi
    "$VENV_PYTHON" -m pip install -r requirements.txt
    # Double ensure just in case requirements.txt was hard-pinned
    "$VENV_PYTHON" -m pip install Flask>=3.1.2 Werkzeug>=3.1.4 blinker>=1.9.0
fi

# Install Node dependencies if needed for local_balancer.js
if [ -f "package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "Installing Node dependencies..."
        npm install
    fi
fi

if type deactivate >/dev/null 2>&1; then deactivate; fi
cd "$ROOT_DIR" || exit

# =====================================================================
# RENDER BACKEND URL - The always-on server that proxies to Pi
# This is your Render deployment URL
# =====================================================================
RENDER_BACKEND_URL="https://movingaverage-sh7s.onrender.com"
HEARTBEAT_SECRET="pi-heartbeat-2024"

# =====================================================================
# CLOUDFLARE CONFIGURATION
# Set PERSISTENT_TUNNEL_URL if you have a custom domain (e.g., api.yourdomain.com)
# =====================================================================
PERSISTENT_TUNNEL_URL="" # Leave empty to use dynamic Quick Tunnel

# Ensure common paths are included (critical for nohup/cron)
export PATH=$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# Try to source NVM if it exists
if [ -f "$HOME/.nvm/nvm.sh" ]; then
    . "$HOME/.nvm/nvm.sh"
fi

# Helper function to get correct python executable
get_python_cmd() {
    cd "$FLASK_DIR" || return
    if [ -f "venv/bin/python3" ]; then
        echo "$FLASK_DIR/venv/bin/python3"
    elif [ -f "env/bin/python3" ]; then
        echo "$FLASK_DIR/env/bin/python3"
    else
        echo "python3"
    fi
}
# Helper function to get correct node executable
get_node_cmd() {
    if command -v node >/dev/null 2>&1; then
        command -v node
    else
        # Search for NVM installed node versions
        local nvm_node=$(find "$HOME/.nvm/versions/node" -name node -type f 2>/dev/null | sort -Vr | head -1)
        if [ -n "$nvm_node" ]; then
            echo "$nvm_node"
        elif [ -f "/usr/bin/node" ]; then
            echo "/usr/bin/node"
        elif [ -f "/usr/local/bin/node" ]; then
            echo "/usr/local/bin/node"
        else
            echo "node"
        fi
    fi
}
PYTHON_CMD=$(get_python_cmd)
NODE_CMD=$(get_node_cmd)

echo "====================================================="
echo " Heartbeat Check: $(date '+%Y-%m-%d %H:%M:%S')"
echo "====================================================="

STATUS=0

# 1. Check Flask Backends (5001-5007)
echo "Checking Flask Backends..."

# Patch app.py to use 0.0.0.0 instead of :: to prevent IPv6 binding crashes on EC2
# Patch local_balancer.js to use 127.0.0.1 instead of localhost for Node 18+ IPv6 bypass
cd "$FLASK_DIR" || exit
if command -v sed >/dev/null 2>&1; then
    sed -i "s/host='::'/host='0.0.0.0'/g" app.py || true
    sed -i "s/const HOST = 'localhost'/const HOST = '127.0.0.1'/g" local_balancer.js || true
fi

# Neutralize the dangerous /healthcheck yfinance network call that causes timeout kills
python3 -c "
import os
if os.path.exists('app.py'):
    with open('app.py', 'r') as f:
        c = f.read()
    c = c.replace('ticker = yf.Ticker(\'RELIANCE.NS\')', 'return jsonify({\"status\": \"healthy\"}), 200\\n        ticker = yf.Ticker(\'RELIANCE.NS\')')
    with open('app.py', 'w') as f:
        f.write(c)
" || true

for port in 5001 5002 5003 5004 5005 5006 5007; do
    # Curl checks if the server responds gracefully (timeout 5s).
    if curl -sf --max-time 5 "http://127.0.0.1:$port/healthcheck" > /dev/null 2>&1; then
        echo "  [OK] Flask $port"
    else
        echo "  [FAIL] Flask $port is down or hung. Restarting..."
        
        # Kill any existing process running on this port
        pid=$(ps aux | grep "[p]ython3 app.py $port" | awk '{print $2}')
        if [ -n "$pid" ]; then
            kill -9 "$pid" 2>/dev/null
        fi
        
        # Restart
        nohup "$PYTHON_CMD" app.py $port > "$LOG_DIR/flask_$port.log" 2>&1 &
        STATUS=1
    fi
done

# 3. Check Service Manager (8081)
echo "Checking Service Manager..."
if curl -sf --max-time 5 "http://localhost:8081/api/system/ping" > /dev/null 2>&1; then
    echo "  [OK] Service Manager 8081"
else
    echo "  [FAIL] Service Manager 8081 is down. Restarting..."
    pkill -f service_manager.py 2>/dev/null
    cd "$FLASK_DIR" || exit
    nohup $PYTHON_CMD service_manager.py > "$LOG_DIR/service_manager.log" 2>&1 &
    STATUS=1
fi

# 4. Check Local Balancer (4001)
echo "Checking Local Balancer..."
CURL_OUT=$(curl -sf --max-time 5 "http://127.0.0.1:4001/health" 2>&1)
if [ $? -eq 0 ]; then
    echo "  [OK] Balancer 4001"
else
    echo "  [FAIL] Balancer 4001 is down (Error: $CURL_OUT). Restarting..."
    sudo fuser -k 4001/tcp 2>/dev/null
    pkill -9 -f local_balancer.js 2>/dev/null
    sleep 1 # Allow port to be released
    cd "$FLASK_DIR" || exit
    if [ -f "local_balancer.js" ]; then
        # Use npm start if package.json exists, otherwise node direct
        nohup $NODE_CMD local_balancer.js > "$LOG_DIR/balancer.log" 2>&1 &
        echo "  [WAIT] Waiting 2s for balancer to bind..."
        sleep 2
        STATUS=1
    else
        echo "  [ERROR] local_balancer.js not found in $FLASK_DIR"
    fi
fi

# 5. Check Cloudflare Tunnel
echo "Checking Cloudflare Tunnel..."
if [ -n "$PERSISTENT_TUNNEL_URL" ]; then
    # Named/Persistent Tunnel Logic
    if systemctl is-active --quiet cloudflared 2>/dev/null || ps aux | grep "[c]loudflared tunnel run" > /dev/null; then
        echo "  [OK] Persistent Cloudflared Service"
    else
        echo "  [FAIL] Persistent Cloudflared is down. Restarting service..."
        sudo systemctl restart cloudflared 2>/dev/null || nohup cloudflared tunnel run moving-average-pi > "$LOG_DIR/cloudflared.log" 2>&1 &
        STATUS=1
    fi
    TUNNEL_URL="https://$PERSISTENT_TUNNEL_URL"
else
    # Quick Tunnel Logic (Dynamic)
    if ps aux | grep "[c]loudflared tunnel --url" > /dev/null; then
        echo "  [OK] Quick Cloudflared process is running"
    else
        echo "  [FAIL] Cloudflared is not running. Starting Quick Tunnel..."
        pkill -9 -f "cloudflared tunnel" 2>/dev/null
        nohup cloudflared tunnel --url http://127.0.0.1:4001 > "$LOG_DIR/cloudflared.log" 2>&1 &
        echo "  [WAIT] Waiting 15s for Cloudflare tunnel to stabilize..."
        sleep 15  # Increased wait for VM performance
        STATUS=1
    fi
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | tail -1)
    
    # Check if the tunnel is actually alive (Fix for 530 Origin Unregistered)
    if [ -n "$TUNNEL_URL" ]; then
        HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}\n" "$TUNNEL_URL")
        if [ "$HTTP_STATUS" = "530" ] || [ "$HTTP_STATUS" = "000" ]; then
            echo "  [FAIL] Tunnel $TUNNEL_URL is dead (Status: $HTTP_STATUS). Regenerating..."
            pkill -9 -f "cloudflared tunnel" 2>/dev/null
            > "$LOG_DIR/cloudflared.log" # Clear old log
            nohup cloudflared tunnel --url http://127.0.0.1:4001 > "$LOG_DIR/cloudflared.log" 2>&1 &
            echo "  [WAIT] Waiting 15s for new Cloudflare tunnel..."
            sleep 15
            TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | tail -1)
            STATUS=1
        else
            echo "  [OK] Tunnel is responding (Status: $HTTP_STATUS)"
        fi
    fi
fi

if [ -z "$TUNNEL_URL" ]; then
    TUNNEL_URL=$(journalctl -u cloudflared --no-pager -n 50 2>/dev/null | grep -o 'https://[a-zA-Z0-9.-]*\.com' | tail -1)
fi

if [ -n "$TUNNEL_URL" ]; then
    echo "  [INFO] Detected tunnel: $TUNNEL_URL"

    # Collect current Pi service status
    BALANCER_STATUS="up"
    FLASK_5001="up"; FLASK_5002="up"; FLASK_5003="up"
    FLASK_5004="up"; FLASK_5005="up"; FLASK_5006="up"; FLASK_5007="up"

    for port in 5001 5002 5003 5004 5005 5006 5007; do
        if ! curl -sf --max-time 3 "http://localhost:$port/healthcheck" > /dev/null 2>&1; then
            eval "FLASK_$port=down"
        fi
    done
    if ! curl -sf --max-time 3 "http://127.0.0.1:4001/health" > /dev/null 2>&1; then
        BALANCER_STATUS="down"
    fi

    UP_COUNT=$(echo "$FLASK_5001 $FLASK_5002 $FLASK_5003 $FLASK_5004 $FLASK_5005 $FLASK_5006 $FLASK_5007 $BALANCER_STATUS" | tr ' ' '\n' | grep -c "up")

    # Build status JSON and push to Render with tunnel URL
    STATUS_JSON="{\"services\":{\"balancer_4001\":\"$BALANCER_STATUS\",\"flask_5001\":\"$FLASK_5001\",\"flask_5002\":\"$FLASK_5002\",\"flask_5003\":\"$FLASK_5003\",\"flask_5004\":\"$FLASK_5004\",\"flask_5005\":\"$FLASK_5005\",\"flask_5006\":\"$FLASK_5006\",\"flask_5007\":\"$FLASK_5007\"},\"status\":\"healthy\",\"total\":9,\"up\":$UP_COUNT,\"tunnel\":\"$TUNNEL_URL\"}"

    RESPONSE=$(curl -sf -X POST "$RENDER_BACKEND_URL/api/register-tunnel" \
        -H "Content-Type: application/json" \
        -d "{\"tunnelUrl\": \"$TUNNEL_URL\", \"secret\": \"$HEARTBEAT_SECRET\", \"status\": $STATUS_JSON}" \
        --max-time 10 2>&1)
    if echo "$RESPONSE" | grep -q 'registered successfully'; then
        echo "  [OK] Status and tunnel URL pushed to Render"
    else
        echo "  [WARN] Failed to push to Render: $RESPONSE"
    fi
else
    echo "  [WARN] Could not detect tunnel URL from cloudflared log."
fi


if [ $STATUS -eq 1 ]; then
    echo "One or more services were restarted. Check logs in $LOG_DIR if issues persist."
else
    echo "All services are running perfectly."
fi
echo ""
