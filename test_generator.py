import os
import sys
from flask import Flask
# Mock flask app for context if needed, though publish_service doesn't seem to need it yet
sys.path.append(os.path.dirname(__file__))

from publish_service import VeoVideoGenerator

def dev_test():
    prompt = "A futuristic stock market dashboard with glowing neon lines, cinematic 9:16"
    symbol = "TEST_STOCK"
    
    print("Initializing VeoVideoGenerator...")
    generator = VeoVideoGenerator()
    
    print(f"Starting generation for {symbol}...")
    filename = generator.generate(prompt, symbol)
    
    if filename:
        print(f"SUCCESS: Video saved as {filename}")
        video_path = os.path.join(os.path.dirname(__file__), 'temp_videos', filename)
        if os.path.exists(video_path):
            print(f"Verified: File exists at {video_path}")
            print(f"Size: {os.path.getsize(video_path)} bytes")
        else:
            print(f"ERROR: File NOT found at {video_path}")
    else:
        print("FAILURE: Video generation failed.")

if __name__ == "__main__":
    dev_test()
