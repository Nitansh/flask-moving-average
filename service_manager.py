import os
import sys
import time
import json
import re
import threading
import subprocess
import urllib.request
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS so the Vercel app can talk directly to this local IP port
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route('/api/system/ping')
def ping():
    return jsonify({"status": "pong", "message": "Pi Service Manager is reachable!"})

# Determine the absolute path of the workspace dynamically
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FLASK_DIR = os.path.join(WORKSPACE_DIR, 'flask-moving-average')
NODE_DIR = os.path.join(WORKSPACE_DIR, 'movingAverage')
CLIENT_DIR = os.path.join(WORKSPACE_DIR, 'movingAverage', 'client')

FLASK_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
CONFIG_FILE = os.path.join(WORKSPACE_DIR, 'service_config.json')

# We'll expect cloudflared to dump its logs here
CLOUDFLARED_LOG = "/tmp/cloudflared.log" if sys.platform != 'win32' else os.path.join(WORKSPACE_DIR, "cloudflared.log")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(data):
    current = load_config()
    current.update(data)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current, f)

# Background Thread for Cloudflare -> Render Sync
def update_render_api(tunnel_url, render_api_key, render_service_id):
    url = f"https://api.render.com/v1/services/{render_service_id}/env-vars"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {render_api_key}"
    }
    payload = json.dumps([
        {
            "key": "FLASK_API_URL",
            "value": tunnel_url
        }
    ]).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='PUT')
        with urllib.request.urlopen(req) as response:
            print(f"[Render Sync] Successfully updated Render FLASK_API_URL to {tunnel_url}")
            return True
    except Exception as e:
        print(f"[Render Sync Error] {e}")
        return False

def cloudflare_sync_thread():
    last_known_url = None
    while True:
        try:
            if os.path.exists(CLOUDFLARED_LOG):
                with open(CLOUDFLARED_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    matches = re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', content)
                    if matches:
                        latest_url = matches[-1]
                        if latest_url != last_known_url:
                            cfg = load_config()
                            if cfg.get('renderApiKey') and cfg.get('renderServiceId'):
                                print(f"[Cloudflare Observer] New tunnel detected: {latest_url}. Syncing to Render...")
                                success = update_render_api(latest_url, cfg['renderApiKey'], cfg['renderServiceId'])
                                if success:
                                    last_known_url = latest_url
                                    # Save current synced url into config
                                    save_config({"currentTunnelUrl": latest_url})
                            else:
                                print(f"[Cloudflare Observer] New tunnel detected ({latest_url}), but Render API config is missing.")
                                last_known_url = latest_url
        except Exception as e:
            pass
        time.sleep(5)

# Start the observer daemon
th = threading.Thread(target=cloudflare_sync_thread, daemon=True)
th.start()


# ---------------------- System Management Functions ----------------------

def check_port(port, path="/healthcheck", timeout=2):
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status == 200
    except:
        return False

def kill_by_pattern(pattern):
    if sys.platform == 'win32':
        # Generic windows taskkill (less granular than linux)
        if "python" in pattern:
            subprocess.run("taskkill /F /IM python.exe", shell=True, capture_output=True)
        elif "node" in pattern:
            subprocess.run("taskkill /F /IM node.exe", shell=True, capture_output=True)
    else:
        try:
            cmd = f"ps aux | grep '{pattern}' | grep -v grep | grep -v service_manager.py | awk '{{print $2}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    os.kill(int(pid), 9)
        except Exception:
            pass
    time.sleep(1)

def start_flask():
    for port in FLASK_PORTS:
        if sys.platform == 'win32':
            subprocess.Popen(f"cd /d {FLASK_DIR} && start /B python app.py {port}", shell=True)
        else:
            python_cmd = "venv/bin/python3" if os.path.exists(os.path.join(FLASK_DIR, "venv")) else "python3"
            subprocess.Popen(
                f"cd {FLASK_DIR} && nohup {python_cmd} app.py {port} > /tmp/flask_{port}.log 2>&1 &",
                shell=True, executable="/bin/bash"
            )

def start_balancer():
    if sys.platform == 'win32':
        subprocess.Popen(f"cd /d {FLASK_DIR} && start /B node local_balancer.js", shell=True)
    else:
        subprocess.Popen(
            f"cd {FLASK_DIR} && nohup node local_balancer.js > /tmp/balancer.log 2>&1 &",
            shell=True, executable="/bin/bash"
        )

# ---------------------- API Endpoints ----------------------

@app.route('/api/system/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        save_config({
            "renderApiKey": data.get("renderApiKey", ""),
            "renderServiceId": data.get("renderServiceId", "")
        })
        return jsonify({"status": "success", "message": "Configuration saved"})
    return jsonify(load_config())

@app.route('/api/system/status')
def status():
    services = {}
    for port in FLASK_PORTS:
        services[f"flask_{port}"] = "up" if check_port(port) else "down"
    
    # Check load balancer on 4000
    services["balancer_4000"] = "up" if check_port(4000, path="/api/system/healthcheck") else "down"

    up = sum(1 for v in services.values() if v == "up")
    total = len(services)
    
    cfg = load_config()
    current_tunnel = cfg.get("currentTunnelUrl", "None Detected")

    return jsonify({
        "status": "healthy" if up == total else "degraded",
        "up": up,
        "total": total,
        "services": services,
        "tunnel": current_tunnel
    })

@app.route('/api/system/healthcheck')
def healthcheck():
    return jsonify({"status": "healthy"}), 200

@app.route('/api/system/restart/<service>', methods=['POST'])
def restart_service(service):
    service = service.lower()
    
    if service == "flask":
        kill_by_pattern("python app.py")
        start_flask()
    elif service == "balancer":
        kill_by_pattern("node local_balancer.js")
        start_balancer()
    elif service == "all":
        kill_by_pattern("python app.py")
        kill_by_pattern("node local_balancer.js")
        start_flask()
        start_balancer()
    else:
        return jsonify({"error": f"Unknown service: {service}"}), 400
    
    # Give them a few seconds to boot before checking
    time.sleep(3)
    
    return status()


if __name__ == '__main__':
    print(f"Service Manager running on port 8080. Workspace: {WORKSPACE_DIR}")
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=8080)
    except ImportError:
        app.run(host='0.0.0.0', port=8080)
