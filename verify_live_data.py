from jugaad_data.nse import NSELive
import requests
import random
import json

class CustomNSELive(NSELive):
    def __init__(self):
        self.base_url = "https://www.nseindia.com/api"
        self.page_url = "https://www.nseindia.com/get-quotes/equity?symbol=INFY"
        self._routes = {
            "stock_meta": "/equity-meta-info",
            "stock_quote": "/quote-equity",
            "stock_derivative_quote": "/quote-derivative",
            "market_status": "/marketStatus",
            "chart_data": "/chart-databyindex",
            "market_turnover": "/market-turnover",
            "equity_derivative_turnover": "/equity-stockIndices",
            "all_indices": "/allIndices",
            "live_index": "/equity-stockIndices",
            "index_option_chain": "/option-chain-indices",
        }
        
        # List of User-Agents to rotate
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0"
        ]
        
        self.s = requests.Session()
        headers = {
            "Host": "www.nseindia.com",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=SBIN",
            "User-Agent": random.choice(self.user_agents),

            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",

            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",

            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",

            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        }
        self.s.headers.update(headers)
        self.s.request = lambda method, url, *args, **kwargs: requests.Session.request(self.s, method, url, *args, timeout=10, **kwargs) # Add global timeout to session
        # Verify initial session setup
        print("Creating session and hitting base page...")
        r = self.s.get(self.page_url)
        print(f"Base page status: {r.status_code}")
        if r.status_code != 200:
            print("Failed to init cookies/session from base page")

def verify_live():
    symbol = "RELIANCE"
    print(f"Testing live fetch for {symbol}...")
    try:
        n = CustomNSELive()
        stockData = n.stock_quote(symbol)
        
        print(f"[SUCCESS]: Fetched data for {symbol}")
        print(f"Current Price: {stockData['priceInfo']['lastPrice']}")
        print(json.dumps(stockData['priceInfo'], indent=2))
    except Exception as e:
        print(f"[ERROR] Failed to fetch live data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_live()
