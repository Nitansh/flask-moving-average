import os
import json
import time
from google import genai
from google.genai import types

def test_veo():
    # Paths
    sa_path = 'c:/moving-average/flask-moving-average/service_account.json'
    config_path = 'c:/moving-average/service_config.json'
    
    if not os.path.exists(sa_path):
        print(f"Error: Service account file not found at {sa_path}")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
    
    project_id = config.get('google_cloud', {}).get('project_id', 'smchatbot-381012')
    print(f"Testing VEO with Project ID: {project_id}")
    
    # Set credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = sa_path
    
    try:
        client = genai.Client(vertexai=True, project=project_id, location='us-central1')
        print("Successfully initialized GenAI client.")
        
        # Test model listing or simple generation
        print("Attempting to list models to verify connectivity...")
        for model in client.models.list():
            if 'veo' in model.name:
                print(f"Found model: {model.name}")
        
        print("\nAttempting short video generation (this might take time)...")
        operation = client.models.generate_videos(
            model="veo-3.1-generate-001",
            prompt="A blue bird flying in the sky, cinematic 9:16",
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
            )
        )
        print(f"Operation started: {operation.name}")
        
        # Poll for a bit
        for _ in range(5):
            print(f"Status: done={operation.done}")
            if operation.done:
                break
            time.sleep(5)
            operation = client.operations.get(operation.name)
        
        if operation.done and operation.result:
             print(f"Success! Video URI: {operation.result.generated_videos[0].video.uri}")
        else:
             print("Operation still in progress or failed. Check console for errors.")
             
    except Exception as e:
        print(f"\n[VEO ERROR] {e}")
        if "403" in str(e):
            print("Tip: Ensure Vertex AI API is enabled and service account has 'Vertex AI User' role.")
        if "404" in str(e):
            print("Tip: Check if the model ID 'veo-3.1-generate-001' is correct and available in us-central1.")

if __name__ == "__main__":
    test_veo()
