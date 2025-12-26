import yfinance as yf
import pandas as pd
from datetime import date
import os
import certifi

# Apply SSL Fix
os.environ['SSL_CERT_FILE'] = certifi.where()

def test_fetch():
    symbol = "RELIANCE.NS"
    print(f"Attempting to fetch {symbol}...")
    try:
        # Fetch last 5 days
        df = yf.download(symbol, period="5d", progress=False)
        if df.empty:
            print("[FAILURE]: Downloaded DataFrame is empty.")
            return
        
        print("[SUCCESS]: Data fetched.")
        print(df.head())
        
        # Check MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            print("[WARNING]: Columns are MultiIndex. Flattening...")
            df.columns = df.columns.get_level_values(0)
            print("Columns after flatten:", df.columns)
        
        df = df.reset_index()
        
        # Rename logic from app.py
        map_cols = {
            'Date': 'DATE',
            'Open': 'OPEN',
            'High': 'HIGH',
            'Low': 'LOW',
            'Close': 'CLOSE',
            'Volume': 'VOLUME'
        }
        df = df.rename(columns=map_cols)
        print("Columns after rename:", df.columns)
        
        if 'CLOSE' in df.columns:
            print("[SUCCESS]: 'CLOSE' column found.")
        else:
            print("[FAILURE]: 'CLOSE' column MISSING. Rename failed.")

    except Exception as e:
        print(f"[CRITICAL ERROR]: {e}")

if __name__ == "__main__":
    test_fetch()
