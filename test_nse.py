from jugaad_data.nse import NSELive
import requests
import random

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

class CustomNSELive(NSELive):
    def __init__(self):
        self.base_url = "https://www.nseindia.com/api"
        self.page_url = "https://www.nseindia.com/get-quotes/equity?symbol=INFY"
        self.user_agents = user_agents
        
        self.s = requests.Session()
        h = {
            "Host": "www.nseindia.com",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=SBIN",
            "X-Requested-With": "XMLHttpRequest",
            "pragma": "no-cache",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "User-Agent": random.choice(self.user_agents),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        self.s.headers.update(h)
        print("Initializing session...")
        self.s.get(self.page_url)
        print("Session initialized.")

try:
    print("Starting test...")
    n = CustomNSELive()
    print("Fetching quote for RELIANCE...")
    q = n.stock_quote("RELIANCE")
    print("Success!")
    print(q['priceInfo']['lastPrice'])
except Exception as e:
    print(f"Error: {e}")
