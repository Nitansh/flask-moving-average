import os
import time
import json
import requests
import asyncio
from typing import List, Optional
from google import genai
from google.genai import types
from telegram import Bot

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
                filename = f"{symbol}_{int(time.time())}.mp4"
                filepath = os.path.join(TEMP_VIDEO_DIR, filename)
                
                # Download the video
                print(f"[VEO] Downloading generated video to {filepath}...")
                resp = requests.get(video_url)
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                return filename
        except Exception as e:
            print(f"[VEO Error] {e}")
            return None

class InstagramPublisher:
    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id
        self.base_url = f"https://graph.facebook.com/v23.0/{self.user_id}"

    def publish(self, video_url: str, caption: str) -> bool:
        print(f"[Instagram] Creating media container for {video_url}...")
        try:
            # 1. Create Media Container
            payload = {
                'video_url': video_url,
                'media_type': 'REELS',
                'caption': caption,
                'access_token': self.access_token
            }
            resp = requests.post(f"{self.base_url}/media", data=payload)
            container_id = resp.json().get('id')
            if not container_id:
                print(f"[Instagram Error] Failed to create container: {resp.json()}")
                return False

            # 2. Poll Status
            while True:
                status_resp = requests.get(
                    f"https://graph.facebook.com/v23.0/{container_id}",
                    params={'fields': 'status_code', 'access_token': self.access_token}
                )
                status = status_resp.json().get('status_code')
                print(f"[Instagram] Progress: {status}")
                if status == 'FINISHED':
                    break
                elif status == 'ERROR':
                    print(f"[Instagram Error] Processing failed: {status_resp.json()}")
                    return False
                time.sleep(5)

            # 3. Publish
            publish_payload = {
                'creation_id': container_id,
                'access_token': self.access_token
            }
            publish_resp = requests.post(f"{self.base_url}/media_publish", data=publish_payload)
            print(f"[Instagram] Reel Published! ID: {publish_resp.json().get('id')}")
            return True
        except Exception as e:
            print(f"[Instagram Error] {e}")
            return False

class TelegramPublisher:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def publish(self, video_path: str, caption: str) -> bool:
        print(f"[Telegram] Sending video to {self.chat_id}...")
        try:
            bot = Bot(token=self.bot_token)
            with open(video_path, 'rb') as video:
                await bot.send_video(
                    chat_id=self.chat_id,
                    video=video,
                    caption=caption,
                    supports_streaming=True
                )
            print("[Telegram] Video sent successfully!")
            return True
        except Exception as e:
            print(f"[Telegram Error] {e}")
            return False

# Placeholder for YouTubePublisher (requires more complex OAuth logic)
class YouTubePublisher:
    def __init__(self, client_secrets_file: str, token_file: str):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file

    def publish(self, video_path: str, title: str, description: str) -> bool:
        print("[YouTube] Publishing Shorts (Not fully implemented - requires OAuth token management)")
        return False
