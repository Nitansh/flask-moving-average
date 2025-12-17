from flask import Flask, jsonify, request
from datetime import date, timedelta, datetime
from jugaad_data.nse import NSELive
from jugaad_data.nse.history import NSEHistory, stock_select_headers, stock_final_headers, stock_dtypes
from finta import TA
from waitress import serve
import pandas as pd
import sys
import requests

import random
from mcap import MCAP, COMPANY_NAME

import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
import yfinance as yf

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
        self.s.get(self.page_url)

import yfinance as yf

# Replaced CustomNSEHistory with yfinance logic
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
        
        # Rename columns to match expected format
        # YFinance returns Date, Open, High, Low, Close, Adj Close, Volume
        df = df.rename(columns={
            'Date': 'DATE',
            'Open': 'OPEN',
            'High': 'HIGH',
            'Low': 'LOW',
            'Close': 'CLOSE',
            'Volume': 'VOLUME'
        })
        
        # Ensure we have the required columns for downstream logic (finta expects lowercase but we can keep uppercase if consistent)
        # The original code mapped to stock_final_headers which were uppercase.
        
        return df
    except Exception as e:
        print(f"Error in custom_stock_df for {symbol}: {e}")
        return pd.DataFrame()

app = Flask(__name__)
# n = CustomNSELive() # Removed global instance
pd.options.mode.copy_on_write = True

PRICE_DIFF_PERCENTAGE = 1
PRICE_DIFF_BEARISH_PERCENTAGE = 5
MCAP_THRESHOLD = 10
TIME_DELTA = -1


def get_live_symbol_df( df ):
    try:
        n = CustomNSELive()
        stockData = n.stock_quote(df['SYMBOL'])
        df['DATE'] = df['DATE']+ timedelta(days=1)
        df['OPEN'] = stockData['priceInfo']['open']
        df['PREV. CLOSE'] = df['CLOSE']
        df['LTP'] = stockData['priceInfo']['lastPrice']
        df['CLOSE'] = stockData['priceInfo']['lastPrice']
        df['VWAP'] = stockData['priceInfo']['vwap']
    except Exception as e:
        print(f"Error in get_live_symbol_df for {df.get('SYMBOL', 'Unknown')}: {e}")
        pass
    return df

@app.route('/healthcheck')
def get_healt_check():
    print("in Health Check")
    df = custom_stock_df(symbol='RELIANCE', from_date=date(2022,7,12), to_date=date(2023,7,12), series="EQ")
    return str(df.iloc[-1]['CLOSE'])

@app.route('/live')
def get_live_stock():
    symbol = request.args.get('symbol')
    print(f"DEBUG: /live request for symbol: {symbol}")
    if ( symbol ):
        try:
            n = CustomNSELive()
            stockData = n.stock_quote(symbol)
            return jsonify({
                'symbol' : symbol,
                'industry' : stockData.get('info').get('industry'),
                'currentPrice' : stockData['priceInfo']['lastPrice']
            })
        except Exception as e:
            print(f"Error fetching live stock for {symbol}: {e}")
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({})

@app.route('/')
def get_dma():
    response = {}
    try:
        stock = request.args.get('symbol')
        print(f"DEBUG: / (DMA) request for symbol: {stock}")
        dma_list = request.args.get('dma').split(',')
        one_day_before = datetime.now() + timedelta(days=-1)
        year = one_day_before.year
        month = one_day_before.month
        day = one_day_before.day
        df = custom_stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
        df = df.iloc[::-1]
        df = df._append( get_live_symbol_df(df.iloc[0]))
        rsi = TA.RSI(df)
        response['symbol'] = stock
        response['id'] = stock
        response['price'] = df.iloc[-1]['CLOSE']
        response['rsi'] = rsi.iloc[-1]
        response['mcap'] = MCAP.get(stock, 0)
        response['name'] = COMPANY_NAME.get(stock, stock)
        response['url'] = 'https://www.screener.in/company/'+ stock +'/consolidated/'
        response['chart'] = 'https://in.tradingview.com/chart/?symbol=NSE%3A'+stock
        for item in dma_list:
            response[item] = TA.DEMA(df, int(item.split('_')[1] ) ).iloc[-1]
        if response['rsi'] > 20 and response['rsi'] < 70 and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50'] and response['price'] > response['DMA_100'] and response['price'] > response['DMA_200']:
            response['isBullish'] = 'true'
    except Exception as e:
        print( "Error occurred in "+stock)
        print(e)

    return jsonify( response )


@app.route('/history')
def get_history():
    try:
        symbol = request.args.get('symbol')
        days = int(request.args.get('days', 365))
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        df = custom_stock_df(
            symbol=symbol, 
            from_date=from_date.date(), 
            to_date=to_date.date(), 
            series="EQ"
        )
        
        # Format for frontend chart
        # Recharts expects array of objects: [{date: '...', price: 100}, ...]
        history_data = []
        for index, row in df.iterrows():
            history_data.append({
                'date': row['DATE'].strftime('%Y-%m-%d'),
                'price': row['CLOSE'],
                'open': row['OPEN'],
                'high': row['HIGH'],
                'low': row['LOW'],
                'volume': row['VOLUME']
            })
            
        return jsonify({
            'symbol': symbol,
            'data': history_data
        })
    except Exception as e:
        print(f"Error fetching history for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/price_diff')
def get_dma_price_diff_bullish():
    response = {}
    stock = request.args.get('symbol')
    dma_list = request.args.get('dma').split(',')
    price_diff_val = int( request.args.get('priceDiff', PRICE_DIFF_PERCENTAGE ) ) * .01 
    price_diff_bearish_val = int( request.args.get('priceDiffBullish', PRICE_DIFF_BEARISH_PERCENTAGE )) *.01
    
    print(f"DEBUG: Processing {stock} | Price: {df.iloc[-1]['CLOSE']} | PriceDiff: {price_diff_val} | BearishDiff: {price_diff_bearish_val}")

    time_delta = int( request.args.get('timeDelta', 0 )) * TIME_DELTA
    one_day_before = datetime.now() + timedelta(days=time_delta)
    year = one_day_before.year
    month = one_day_before.month
    day = one_day_before.day
    df = custom_stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
    df = df.iloc[::-1]
    df = df._append( get_live_symbol_df(df.iloc[0]))
    rsi = TA.RSI(df)

    response['symbol'] = stock
    response['id'] = stock
    response['price'] = df.iloc[-1]['CLOSE']
    response['rsi'] = rsi.iloc[-1]
    response['mcap'] = MCAP.get(stock, 0)
    response['name'] = COMPANY_NAME.get(stock, stock)
    response['url'] = 'https://www.screener.in/company/'+ stock +'/consolidated/'
    response['chart'] = 'https://in.tradingview.com/chart/?symbol=NSE%3A'+stock
    for item in dma_list:
        response[item] = TA.DEMA(df, int(item.split('_')[1] ) ).iloc[-1]
    
    # Debug Logic
    dma20 = response.get('DMA_20', 0)
    dma50 = response.get('DMA_50', 0)
    dma100 = response.get('DMA_100', 0)
    price = response['price']

    # Bullish Condition Debug
    cond1 = response['mcap'] > MCAP_THRESHOLD
    cond2 = price > dma20 and price > dma50 and price > dma100
    diff1 = abs(dma20 - dma50)
    limit1 = (price * price_diff_val)
    cond3 = diff1 < limit1
    diff2 = abs(dma50 - dma100)
    limit2 = (price * price_diff_val)
    cond4 = diff2 < limit2
    
    if cond1 and cond2 and cond3 and cond4:
        response['isBullish'] = 'true'
        print(f"MATCH BULLISH: {stock}")
    else:
        # print(f"FAIL BULLISH {stock}: MCAP={cond1} PRICE>DMA={cond2} DIFF1({diff1:.2f}<{limit1:.2f})={cond3} DIFF2({diff2:.2f}<{limit2:.2f})={cond4}")
        pass

    if response['mcap'] > MCAP_THRESHOLD and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50']  and response['price'] > response['DMA_100']  and abs(response['price'] - response['DMA_20']) > (response['price'] * price_diff_bearish_val) and abs(response['DMA_20'] - response['DMA_50']) > (response['DMA_20'] * price_diff_bearish_val):
        response['isBearish'] = 'true'
        print(f"MATCH BEARISH: {stock}")

    return jsonify( response )
    
if __name__ == '__main__':
    port = sys.argv[1]
    serve(app, host='0.0.0.0', port=port)
