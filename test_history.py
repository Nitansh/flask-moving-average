from jugaad_data.nse.history import NSEHistory, stock_select_headers, stock_final_headers, stock_dtypes
from datetime import date, timedelta, datetime
import pandas as pd
import requests

class CustomNSEHistory(NSEHistory):
    def __init__(self):
        super().__init__()
        self.headers = {
            "Host": "www.nseindia.com",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=INFY",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
             "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self.s.headers.update(self.headers)

def custom_stock_df(symbol, from_date, to_date):
    h = CustomNSEHistory()
    print(f"Fetching history for {symbol} from {from_date} to {to_date}...")
    raw = h.stock_raw(symbol, from_date, to_date, "EQ")
    print(f"Raw data received: {len(raw)} records")
    return pd.DataFrame(raw)

if __name__ == "__main__":
    try:
        print("Starting History Test...")
        df = custom_stock_df('RELIANCE', date(2025, 1, 1), date(2025, 1, 10))
        print("Success!")
        print(df.head())
    except Exception as e:
        print(f"Error: {e}")
