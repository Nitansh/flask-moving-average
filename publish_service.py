import os
import time
import json
import requests
import asyncio
from typing import List, Optional
from google import genai
from google.genai import types
from telegram_notifier import send_alert

# To be replaced with actual credentials from config
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'service_config.json'))
TEMP_VIDEO_DIR = os.path.join(os.path.dirname(__file__), 'temp_videos')

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}

class VeoVideoGenerator:
    def __init__(self):
        # Ensure temp directory exists
        os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
        print(f"[VEO] Temp video directory: {TEMP_VIDEO_DIR}")
        
        config = load_config()
        sa_path = os.path.join(os.path.dirname(__file__), 'service_account.json')
        
        # Set environment variable for the SDK to pick up
        if os.path.exists(sa_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = sa_path
            print(f"[VEO] Using Service Account: {sa_path}")
        
        project_id = config.get('google_cloud', {}).get('project_id', 'smchatbot-381012')
        self.client = genai.Client(vertexai=True, project=project_id, location='us-central1')
        self.model_id = "veo-3.1-generate-001"

    def generate(self, prompt: str, symbol: str) -> Optional[str]:
        print(f"[VEO] Starting generation for {symbol}...")
        try:
            config = types.GenerateVideosConfig(
                aspect_ratio="9:16",
                number_of_videos=1,
            )
            
            operation = self.client.models.generate_videos(
                model=self.model_id,
                prompt=prompt,
                config=config
            )

            # Polling for completion
            while not operation.done:
                print(f"[VEO] Generation for {symbol} in progress...")
                time.sleep(10)
                operation = self.client.operations.get(operation.name)

            if operation.result:
                video_url = operation.result.generated_videos[0].video.uri
                print(f"[VEO] Video generation successful. URI: {video_url}")
                
                filename = f"{symbol}_{int(time.time())}.mp4"
                filepath = os.path.join(TEMP_VIDEO_DIR, filename)
                
                # Download the video
                print(f"[VEO] Downloading generated video to {filepath}...")
                resp = requests.get(video_url, timeout=60)
                resp.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                
                print(f"[VEO] Download complete: {filename} ({os.path.getsize(filepath)} bytes)")
                return filename
            else:
                print(f"[VEO] Operation finished but no result found for {symbol}")
        except Exception as e:
            print(f"[VEO Error] {e}")
            import traceback
            traceback.print_exc()
            return None

class TelegramPublisher:
    def __init__(self):
        # No local credentials needed, everything is handled by Render Gateway
        pass

    def publish(self, video_url: str, caption: str) -> bool:
        print(f"[Telegram] Proxying video alert to Render Gateway...")
        return send_alert(message=caption, video_url=video_url)
