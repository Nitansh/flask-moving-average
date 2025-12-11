import yfinance as yf
import pandas as pd
from datetime import date
import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()

def custom_stock_df(symbol, from_date, to_date, series="EQ"):
    try:
        ticker = f"{symbol}.NS"
        print(f"Downloading data for {ticker} from {from_date} to {to_date}")
        df = yf.download(ticker, start=from_date, end=to_date, progress=False)
        
        if df.empty:
            print(f"No data found for {ticker}")
            return pd.DataFrame()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        
        df = df.rename(columns={
            'Date': 'DATE',
            'Open': 'OPEN',
            'High': 'HIGH',
            'Low': 'LOW',
            'Close': 'CLOSE',
            'Volume': 'VOLUME'
        })
        
        return df
    except Exception as e:
        print(f"Error in custom_stock_df for {symbol}: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    df = custom_stock_df("RELIANCE", date(2025, 1, 1), date(2025, 1, 10))
    print(df.head())
    print("Columns:", df.columns)
