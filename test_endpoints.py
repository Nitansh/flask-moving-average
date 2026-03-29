import requests
import time
import sys

BASE_URL = "http://localhost:5001"

def test_live():
    url = f"{BASE_URL}/live?symbol=RELIANCE"
    print(f"Testing {url}...")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        if response.status_code == 200 and 'currentPrice' in response.json():
             return True
        return False
    except Exception as e:
        print(f"Failed: {e}")
        return False

def test_dma():
    url = f"{BASE_URL}/?symbol=RELIANCE&dma=DMA_20"
    print(f"Testing {url}...")
    try:
        response = requests.get(url, timeout=20) # fetching history might take longer
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        if response.status_code == 200 and 'price' in response.json():
             return True
        return False
    except Exception as e:
        print(f"Failed: {e}")
        return False

if __name__ == "__main__":
    time.sleep(3) # Wait for app to start
    live_ok = test_live()
    dma_ok = test_dma()
    
    if live_ok and dma_ok:
        print("VERIFICATION SUCCESSFUL")
        sys.exit(0)
    else:
        print("VERIFICATION FAILED")
        sys.exit(1)
