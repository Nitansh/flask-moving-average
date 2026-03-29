from flask import Flask
from datetime import date, timedelta, datetime
from jugaad_data.nse import NSELive
import pandas as pd
import yfinance as yf
import requests
import random

# Mocking the necessary parts of app.py

class CustomNSELive(NSELive):
    def __init__(self):
        self.base_url = "https://www.nseindia.com/api"
        self.page_url = "https://www.nseindia.com/get-quotes/equity?symbol=INFY"
        self._routes = {
             "stock_meta": "/equity-meta-info",
             "stock_quote": "/quote-equity",
        }
        self.user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
        self.s = requests.Session()
        h = {
            "Host": "www.nseindia.com",
            "User-Agent": self.user_agents[0],
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        self.s.headers.update(h)
        self.s.get(self.page_url)

n = CustomNSELive()

def custom_stock_df(symbol, from_date, to_date, series="EQ"):
    try:
        ticker = f"{symbol}.NS"
        print(f"Downloading data for {ticker} from {from_date} to {to_date}")
        df = yf.download(ticker, start=from_date, end=to_date, progress=False, auto_adjust=False) # Trying auto_adjust variations if needed
        
        if df.empty:
            print(f"No data found for {ticker}")
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df = df.rename(columns={
            'Date': 'DATE', 'Open': 'OPEN', 'High': 'HIGH', 'Low': 'LOW', 'Close': 'CLOSE', 'Volume': 'VOLUME'
        })
        return df
    except Exception as e:
        print(f"Error in custom_stock_df for {symbol}: {e}")
        return pd.DataFrame()

def get_live_symbol_df(df, symbol):
    try:
        print(f"Fetching live data for {symbol}")
        # n = CustomNSELive()
        stockData = n.stock_quote(symbol)
        last_price = stockData['priceInfo']['lastPrice']
        print(f"Live Price for {symbol}: {last_price}")
        
        # Simulating the app.py logic which might be failing
        # In app.py: stockData = n.stock_quote(df['SYMBOL']) -> likely fails because SYMBOL is missing
        
        # Manually updating df
        df = df.copy() # Avoid SettingWithCopy
        df['DATE'] = df['DATE'] + timedelta(days=1)
        df['CLOSE'] = last_price
        df['LTP'] = last_price
        return df
    except Exception as e:
        print(f"Error in get_live_symbol_df: {e}")
        return df

def debug_pnb():
    symbol = "PNB"
    today = datetime.now()
    one_year_ago = today - timedelta(days=365)
    
    print("--- 1. Fetching Historical Data (YFinance) ---")
    df = custom_stock_df(symbol, one_year_ago, today)
    if not df.empty:
        print("Historical Data Last 5 Rows:")
        print(df.tail())
        last_hist_price = df.iloc[-1]['CLOSE']
        print(f"Last Historical Close: {last_hist_price}")
    else:
        print("Empty Historical Data")
        return

    print("\n--- 2. Fetching Live Data (NSE) ---")
    try:
        stockData = n.stock_quote(symbol)
        live_price = stockData['priceInfo']['lastPrice']
        print(f"Direct NSE Live Price: {live_price}")
    except Exception as e:
        print(f"NSE Fetch Failed: {e}")

    print("\n--- 3. Simulating App Logic ---")
    # This matches the app.py flaw where df['SYMBOL'] is accessed
    try:
        # In app.py: df = df.iloc[::-1]
        df_rev = df.iloc[::-1]
        latest_row = df_rev.iloc[0]
        
        print("Trying to access latest_row['SYMBOL']...")
        # This should fail
        sym = latest_row['SYMBOL'] 
        print(f"Symbol found: {sym}")
    except Exception as e:
        print(f"Caught Expected Error in App Logic: {e}")
        print("This confirms the app falls back to historical data if live fetch fails.")

if __name__ == "__main__":
    debug_pnb()
