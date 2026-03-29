import requests
import sys

def check_url(url, timeout=5):
    print(f"Checking {url}...")
    try:
        response = requests.get(url, timeout=timeout)
        print(f"SUCCESS: {url} returned {response.status_code}")
        return True
    except Exception as e:
        print(f"FAILURE: {url} failed with {type(e).__name__}: {e}")
        return False

def check_yfinance():
    print("Checking yfinance...")
    try:
        import yfinance as yf
        ticker = yf.Ticker("RELIANCE.NS")
        info = ticker.fast_info
        price = info.last_price
        print(f"SUCCESS: yfinance fetched RELIANCE.NS price: {price}")
        return True
    except Exception as e:
        print(f"FAILURE: yfinance failed: {e}")
        return False

if __name__ == "__main__":
    google = check_url("https://www.google.com")
    nse = check_url("https://www.nseindia.com", timeout=10)
    yf_status = check_yfinance()
    
    if not google:
        print("CRITICAL: No internet access to Google.")
    if google and not nse:
        print("CRITICAL: Internet works, but NSE is unreachable.")
