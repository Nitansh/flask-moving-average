import requests
import os

# Configuration (Injected from Pi environments or hardcoded as per heartbeat.sh)
RENDER_URL = "https://movingaverage-sh7s.onrender.com"
SECRET = "pi-heartbeat-2024"

def send_alert(message):
    """
    Sends a notification to Telegram by proxying through the Render Gateway.
    This keeps the Telegram Bot Token secure on Render.
    """
    endpoint = f"{RENDER_URL}/api/notify/telegram"
    payload = {
        "message": message,
        "secret": SECRET
    }
    
    try:
        print(f"[Notifier] Sending alert to Render: {message[:50]}...")
        resp = requests.post(endpoint, json=payload, timeout=10)
        if resp.status_code == 200:
            print("[Notifier] Alert sent successfully via Render.")
            return True
        else:
            print(f"[Notifier Error] Render returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[Notifier Error] Failed to connect to Render: {e}")
        return False

if __name__ == "__main__":
    # Diagnostic test
    send_alert("🚀 *Diagnostic Test*\nThis message was triggered from the Pi and sent via Render Node.js!")
