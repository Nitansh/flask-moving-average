import yfinance as yf
import json

def check_fields():
    symbol = "RELIANCE.NS"
    ticker = yf.Ticker(symbol)
    
    print("Fetching info...")
    try:
        info = ticker.info
        # print keys to avoid spamming
        print("Info keys:", info.keys())
        
        industry = info.get('industry', 'N/A')
        currentPrice = info.get('currentPrice', info.get('regularMarketPrice', 'N/A'))
        openPrice = info.get('open', info.get('regularMarketOpen', 'N/A'))
        vwap = info.get('vwap', 'N/A') # yf might not have vwap directly in info?
        
        print(f"Industry: {industry}")
        print(f"Current Price: {currentPrice}")
        print(f"Open: {openPrice}")
        print(f"VWAP: {vwap}")
        
    except Exception as e:
        print(f"Error fetching info: {e}")

    print("\nFetching fast_info...")
    try:
        fast_info = ticker.fast_info
        print(f"Last Price: {fast_info.last_price}")
        print(f"Open: {fast_info.open}")
        # fast_info doesn't have industry usually
    except Exception as e:
        print(f"Error fetching fast_info: {e}")

if __name__ == "__main__":
    check_fields()
