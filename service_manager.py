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
try:
    from waitress import serve
except ImportError:
    serve = None

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
ALLOWED_PORTS = [4000, 8080] + FLASK_PORTS
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
    # Safe update endpoint for a single variable
    url = f"https://api.render.com/v1/services/{render_service_id}/env-vars/FLASK_API_URL"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {render_api_key}"
    }
    # Render expects a simple { "value": "..." } for single variable PUT
    payload = json.dumps({"value": tunnel_url}).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='PUT')
        with urllib.request.urlopen(req) as response:
            print(f"[Render Sync] Successfully updated FLASK_API_URL to: {tunnel_url}")
            return True
    except Exception as e:
        print(f"[Render Sync Error] Variable update failed: {e}")
        return False

def trigger_render_deploy(render_api_key, render_service_id):
    url = f"https://api.render.com/v1/services/{render_service_id}/deploys"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {render_api_key}"
    }
    # Optional clearCache param
    payload = json.dumps({"clearCache": "do_not_clear"}).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            print(f"[Render Deploy] Triggered fresh deployment successfully!")
            return True
    except Exception as e:
        print(f"[Render Deploy Error] Failed to trigger deploy: {e}")
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
                                    # Trigger the deploy 2 seconds later to be safe
                                    time.sleep(2)
                                    trigger_render_deploy(cfg['renderApiKey'], cfg['renderServiceId'])
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

def get_pid_for_port(port):
    try:
        if sys.platform == 'win32':
            # Windows netstat -ano findstr :port
            cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
            output = subprocess.check_output(cmd, shell=True).decode()
            if output:
                # PID is the last element
                return int(output.strip().split()[-1])
        else:
            # Linux fuser
            cmd = f"fuser {port}/tcp 2>/dev/null"
            output = subprocess.check_output(cmd, shell=True).decode()
            if output:
                return int(output.strip())
    except:
        pass
    return None

def kill_port(port):
    if port not in ALLOWED_PORTS:
        print(f"[Security Warning] Blocked attempt to kill unauthorized port: {port}")
        return
        
    if sys.platform == 'win32':
        try:
            cmd = f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port} ^| findstr LISTENING\') do taskkill /f /pid %a'
            subprocess.run(cmd, shell=True, capture_output=True)
        except:
            pass
    else:
        try:
            # -k sends KILL signal, -n identifies by numeric port
            subprocess.run(f"fuser -k {port}/tcp", shell=True, capture_output=True)
        except:
            pass
    time.sleep(1)

def start_flask():
    for port in FLASK_PORTS:
        start_flask_port(port)

def start_flask_port(port):
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
        is_up = check_port(port)
        services[f"flask_{port}"] = {
            "status": "up" if is_up else "down",
            "pid": get_pid_for_port(port) if is_up else None
        }
    
    # Check load balancer on 4000
    lb_up = check_port(4000, path="/api/system/healthcheck")
    services["balancer_4000"] = {
        "status": "up" if lb_up else "down",
        "pid": get_pid_for_port(4000) if lb_up else None
    }

    up = sum(1 for v in services.values() if v["status"] == "up")
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
    # Use any available flask port to verify data fetch pipeline
    for port in FLASK_PORTS:
        if check_port(port):
            return jsonify({"status": "healthy", "source": f"flask_{port}"}), 200
    return jsonify({"status": "degraded", "message": "All flask workers failed deep health fetch"}), 503

@app.route('/api/system/kill/<path:service>', methods=['POST'])
def kill_service(service):
    service = service.lower()
    
    if service.startswith("flask/"):
        try:
            port = int(service.split("/")[1])
            kill_port(port)
        except:
            return jsonify({"error": "Invalid port format"}), 400
    elif service == "flask":
        for port in FLASK_PORTS:
            kill_port(port)
    elif service == "balancer":
        kill_port(4000)
    elif service == "all":
        for port in ALLOWED_PORTS:
            if port != 8080: # Don't kill the manager itself via 'all'
                kill_port(port)
    else:
        return jsonify({"error": f"Unknown service or unauthorized: {service}"}), 400
        
    return status()

@app.route('/api/system/restart/<path:service>', methods=['POST'])
def restart_service(service):
    service = service.lower()
    
    if service.startswith("flask/"):
        try:
            port = int(service.split("/")[1])
            kill_port(port)
            start_flask_port(port)
        except:
            return jsonify({"error": "Invalid port"}), 400
    elif service == "flask":
        for port in FLASK_PORTS:
            kill_port(port)
        start_flask()
    elif service == "balancer":
        kill_port(4000)
        start_balancer()
    elif service == "all":
        for port in FLASK_PORTS:
            kill_port(port)
        kill_port(4000)
        start_flask()
        start_balancer()
    else:
        return jsonify({"error": f"Unknown service: {service}"}), 400
    
    # Give them a few seconds to boot before checking
    time.sleep(2)
    
    return status()


if __name__ == '__main__':
    print(f"Service Manager running on port 8080. Workspace: {WORKSPACE_DIR}")
    try:
        # host='::' with threads=4 for robust dual-stack performance on Pi
        print(f"Waitress starting on [::]:8080 (IPv4 + IPv6)...")
        serve(app, host='::', port=8080, threads=4)
    except ImportError:
        app.run(host='::', port=8080)
