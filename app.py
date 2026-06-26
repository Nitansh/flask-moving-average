from flask import Flask, jsonify, request, send_from_directory
from datetime import date, timedelta, datetime
from finta import TA
from waitress import serve
import pandas as pd
import sys
import requests
import time
from functools import wraps

import random
import os
import json
from mcap import MCAP, COMPANY_NAME
from publish_service import VeoVideoGenerator, TelegramPublisher, load_config
import asyncio
import threading
from flask_cors import CORS

# Simple route/endpoint caching decorator
def cache_endpoint(ttl_seconds=300):
    def decorator(f):
        cache = {}
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Use full path including query parameters as cache key
            key = request.full_path
            now = time.time()
            if key in cache:
                val, expires = cache[key]
                if now < expires:
                    return val
            response = f(*args, **kwargs)
            cache[key] = (response, now + ttl_seconds)
            return response
        return decorated_function
    return decorator

# Load industry mapping from nifty500.csv
INDUSTRY_MAP = {}
INDUSTRY_CACHE_FILE = 'industry_cache.json'
try:
    nifty_df = pd.read_csv('nifty500.csv')
    for _, row in nifty_df.iterrows():
        INDUSTRY_MAP[row['Symbol']] = row['Industry']
except Exception as e:
    print(f"Error loading nifty500.csv: {e}")

# Load persistent cache for symbols not in Nifty 500
industry_cache = {}
if os.path.exists(INDUSTRY_CACHE_FILE):
    try:
        with open(INDUSTRY_CACHE_FILE, 'r') as f:
            industry_cache = json.load(f)
    except: pass

# Load persistent cache for ex-dividend dates
EX_DIVIDEND_CACHE_FILE = 'ex_dividend_cache.json'
ex_dividend_cache = {}
ex_dividend_cache_lock = threading.Lock()

if os.path.exists(EX_DIVIDEND_CACHE_FILE):
    try:
        with open(EX_DIVIDEND_CACHE_FILE, 'r') as f:
            ex_dividend_cache = json.load(f)
    except Exception as e:
        print(f"Error loading ex_dividend_cache.json: {e}")

def save_ex_dividend_cache():
    try:
        with open(EX_DIVIDEND_CACHE_FILE, 'w') as f:
            json.dump(ex_dividend_cache, f)
    except Exception as e:
        print(f"Error saving ex_dividend_cache.json: {e}")

def get_ex_dividend_date(symbol):
    if not symbol:
        return None
    current_time = time.time()
    # Cache for 24 hours (86400 seconds)
    cache_ttl = 24 * 60 * 60
    
    with ex_dividend_cache_lock:
        if symbol in ex_dividend_cache:
            cached_data = ex_dividend_cache[symbol]
            # Check if cache is not expired
            if current_time - cached_data.get('fetched_at', 0) < cache_ttl:
                return cached_data.get('date')
    
    # Cache miss or expired
    ex_date_str = None
    try:
        ticker_symbol = f"{symbol}.NS"
        ticker = yf.Ticker(ticker_symbol)
        
        # Method 1: Try ticker.calendar (which is fast)
        cal = ticker.calendar
        if cal and 'Ex-Dividend Date' in cal:
            ex_date = cal['Ex-Dividend Date']
            if ex_date:
                if isinstance(ex_date, (datetime, date)):
                    ex_date_str = ex_date.strftime('%Y-%m-%d')
                else:
                    ex_date_str = str(ex_date)
                    
        # Method 2: Try ticker.info fallback if method 1 failed
        if not ex_date_str:
            info = ticker.info
            ex_div_epoch = info.get('exDividendDate')
            if ex_div_epoch:
                dt = datetime.fromtimestamp(ex_div_epoch)
                ex_date_str = dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Error fetching ex_dividend_date for {symbol}: {e}")
        
    with ex_dividend_cache_lock:
        ex_dividend_cache[symbol] = {
            'date': ex_date_str,
            'fetched_at': current_time
        }
        save_ex_dividend_cache()
        
    return ex_date_str

def get_industry_with_fallback(symbol):
    if symbol in INDUSTRY_MAP:
        return INDUSTRY_MAP[symbol]
    if symbol in industry_cache:
        return industry_cache[symbol]
    
    # Fallback to yfinance (slow, so we cache it)
    try:
        print(f"[Industry Fallback] Fetching for {symbol}...")
        info = yf.Ticker(f"{symbol}.NS").info
        ind = info.get('industry', 'Unknown Sector')
        industry_cache[symbol] = ind
        # Save cache
        with open(INDUSTRY_CACHE_FILE, 'w') as f:
            json.dump(industry_cache, f)
        return ind
    except:
        return 'Unknown Sector'

# Redundant auth logic removed, now handled by Node Gateway on Render
# from auth import verify_google_token, generate_jwt, login_required, admin_required, create_user, get_user, check_trial_status, ADMIN_EMAIL

import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
import yfinance as yf


# Valid headers for yfinance
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


YF_DOWNLOAD_LOCK = threading.Lock()

# Replaced CustomNSEHistory with yfinance logic
def custom_stock_df(symbol, from_date, to_date, series="EQ"):
    try:
        ticker = f"{symbol}.NS"
        
        # Acquire download lock to stagger simultaneous Yahoo requests
        with YF_DOWNLOAD_LOCK:
            time.sleep(0.15)
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
        df = df.rename(columns={
            'Date': 'DATE',
            'Open': 'OPEN',
            'High': 'HIGH',
            'Low': 'LOW',
            'Close': 'CLOSE',
            'Volume': 'VOLUME'
        })
        
        df['SYMBOL'] = symbol
        df = df.dropna(subset=['CLOSE'])
        return df
    except Exception as e:
        print(f"Error in custom_stock_df for {symbol}: {e}")
        return pd.DataFrame()

app = Flask(__name__)
CORS(app) # Enable CORS for frontend
# pd.options.mode.copy_on_write = True  # Removed: always enabled in pandas >= 3.0

PRICE_DIFF_PERCENTAGE = 3
PRICE_DIFF_BEARISH_PERCENTAGE = 5
MCAP_THRESHOLD = 10
TIME_DELTA = -1

def get_live_symbol_df(last_row, symbol, today):
    try:
        ticker_symbol = f"{symbol}.NS"
        ticker = yf.Ticker(ticker_symbol)

        fast_info = ticker.fast_info
        last_price = fast_info.last_price

        if last_price is None:
            last_price = ticker.info.get('currentPrice', 0)

        open_price = fast_info.open
        if open_price is None:
            open_price = ticker.info.get('open', 0)

        # Get high-precision live volume
        live_volume = None
        try:
            live_volume = fast_info.last_volume
        except Exception as vol_err:
            print(f"Warning: fast_info.last_volume failed for {symbol}: {vol_err}")

        if live_volume is None or pd.isna(live_volume) or live_volume == 0:
            try:
                live_volume = ticker.info.get('volume', ticker.info.get('regularMarketVolume', 0))
            except Exception as info_err:
                print(f"Warning: info fallback failed for volume of {symbol}: {info_err}")
                live_volume = 0

        # Convert Series to dict
        row_dict = last_row.to_dict()

        # Modify values
        row_dict['DATE'] = today
        row_dict['OPEN'] = open_price
        row_dict['PREV. CLOSE'] = row_dict['CLOSE']
        row_dict['LTP'] = last_price
        row_dict['CLOSE'] = last_price
        row_dict['VWAP'] = last_price

        if live_volume is not None and not pd.isna(live_volume):
            row_dict['VOLUME'] = int(live_volume)
        else:
            row_dict['VOLUME'] = 0

        # Return proper DataFrame
        return pd.DataFrame([row_dict])

    except Exception as e:
        print(f"Error in get_live_symbol_df: {e}")
        return pd.DataFrame()


@app.route('/healthcheck')
def get_health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/live')
def get_live_stock():
    symbol = request.args.get('symbol')
    print(f"DEBUG: /live request for symbol: '{symbol}'")
    if symbol:
        try:
            ticker_symbol = f"{symbol}.NS"
            ticker = yf.Ticker(ticker_symbol)
            
            # Get industry using our cached helper (much faster and avoids yfinance info limits)
            industry = get_industry_with_fallback(symbol)

            # Calculate dates for 1 year of history
            today = datetime.now().date()
            from_date = today - timedelta(days=365)
            to_date = today + timedelta(days=1)
            
            # Fetch using custom_stock_df
            df = custom_stock_df(symbol=symbol, from_date=from_date, to_date=to_date, series="EQ")

            # High-precision current price derivation
            current_price = None
            
            # Try fast_info first (fastest and standard for real-time yfinance price)
            try:
                current_price = ticker.fast_info.last_price
            except Exception as fast_err:
                print(f"Warning: fast_info failed for {symbol}: {fast_err}")

            # Try history fallback
            if (current_price is None or pd.isna(current_price) or current_price == 0) and not df.empty:
                current_price = df['CLOSE'].iloc[-1]

            # Try ticker.info as a last resort fallback
            if current_price is None or pd.isna(current_price) or current_price == 0:
                try:
                    info = ticker.info
                    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                except Exception as info_err:
                    print(f"Warning: Ticker info fallback failed for {symbol}: {info_err}")
                    current_price = 0

            # Clean and round price
            if current_price is not None and not pd.isna(current_price):
                current_price = round(float(current_price), 2)
            else:
                current_price = 0
            
            # Fetch high-precision live volume
            current_volume = None
            try:
                current_volume = ticker.fast_info.last_volume
            except Exception as fast_vol_err:
                print(f"Warning: fast_info.last_volume failed for {symbol}: {fast_vol_err}")

            if current_volume is None or pd.isna(current_volume) or current_volume == 0:
                try:
                    if not df.empty:
                        current_volume = df['VOLUME'].iloc[-1]
                except Exception as hist_vol_err:
                    print(f"Warning: history fallback failed for volume of {symbol}: {hist_vol_err}")

            if current_volume is None or pd.isna(current_volume) or current_volume == 0:
                try:
                    info = ticker.info
                    current_volume = info.get('volume', info.get('regularMarketVolume', 0))
                except Exception as info_vol_err:
                    print(f"Warning: Ticker info volume fallback failed for {symbol}: {info_vol_err}")
                    current_volume = 0

            if current_volume is not None and not pd.isna(current_volume):
                current_volume = int(current_volume)
            else:
                current_volume = 0

            # If custom_stock_df failed/returned empty, fallback to ticker.history as safety fallback
            if df.empty:
                print(f"Warning: custom_stock_df returned empty for {symbol}, falling back to ticker.history(period='1y')")
                hist = ticker.history(period="1y")
                # Format to look like custom_stock_df output
                if not hist.empty:
                    df = hist.reset_index()
                    df = df.rename(columns={
                        'Date': 'DATE',
                        'Open': 'OPEN',
                        'High': 'HIGH',
                        'Low': 'LOW',
                        'Close': 'CLOSE',
                        'Volume': 'VOLUME'
                    })
                    df['SYMBOL'] = symbol

            # Append live price row to the end of history for real-time RSI & DEMA calculations
            if not df.empty:
                try:
                    last_row_date = df.iloc[-1]['DATE']
                    if isinstance(last_row_date, pd.Timestamp):
                        last_row_date = last_row_date.date()
                    elif isinstance(last_row_date, str):
                        last_row_date = datetime.strptime(last_row_date.split(' ')[0], '%Y-%m-%d').date()

                    if last_row_date < today:
                        last_row = df.iloc[-1]
                        row_dict = last_row.to_dict()
                        row_dict['DATE'] = today
                        row_dict['OPEN'] = current_price
                        row_dict['PREV. CLOSE'] = row_dict['CLOSE']
                        row_dict['LTP'] = current_price
                        row_dict['CLOSE'] = current_price
                        row_dict['VWAP'] = current_price
                        row_dict['VOLUME'] = current_volume
                        
                        live_row = pd.DataFrame([row_dict])
                        df = pd.concat([df, live_row], ignore_index=True)
                    else:
                        df.loc[df.index[-1], 'CLOSE'] = current_price
                        df.loc[df.index[-1], 'VOLUME'] = current_volume
                except Exception as append_err:
                    print(f"Error appending live row for {symbol}: {append_err}")

            rsi_val = None
            if not df.empty and len(df) > 14:
                try:
                    rsi_series = TA.RSI(df)
                    last_rsi = rsi_series.iloc[-1]
                    rsi_val = round(float(last_rsi), 2) if not pd.isna(last_rsi) else None
                except Exception as rsi_err:
                    print(f"Error calculating RSI for {symbol}: {rsi_err}")

            # Calculate DEMA indicators for real-time portfolio/watchlist view without loading flags
            dma20 = None
            dma50 = None
            dma100 = None
            dma200 = None
            if not df.empty:
                try:
                    dma20_series = TA.DEMA(df, 20)
                    if not dma20_series.empty:
                        dma20 = round(float(dma20_series.iloc[-1]), 2) if not pd.isna(dma20_series.iloc[-1]) else None
                except Exception as dema_err:
                    print(f"Error calculating DEMA 20 for {symbol}: {dema_err}")

                try:
                    dma50_series = TA.DEMA(df, 50)
                    if not dma50_series.empty:
                        dma50 = round(float(dma50_series.iloc[-1]), 2) if not pd.isna(dma50_series.iloc[-1]) else None
                except Exception as dema_err:
                    print(f"Error calculating DEMA 50 for {symbol}: {dema_err}")

                try:
                    dma100_series = TA.DEMA(df, 100)
                    if not dma100_series.empty:
                        dma100 = round(float(dma100_series.iloc[-1]), 2) if not pd.isna(dma100_series.iloc[-1]) else None
                except Exception as dema_err:
                    print(f"Error calculating DEMA 100 for {symbol}: {dema_err}")

                try:
                    dma200_series = TA.DEMA(df, 200)
                    if not dma200_series.empty:
                        dma200 = round(float(dma200_series.iloc[-1]), 2) if not pd.isna(dma200_series.iloc[-1]) else None
                except Exception as dema_err:
                    print(f"Error calculating DEMA 200 for {symbol}: {dema_err}")

            return jsonify({
                'symbol' : symbol,
                'industry' : industry,
                'currentPrice' : current_price,
                'rsi': rsi_val,
                'volume': current_volume,
                'DMA_20': dma20,
                'DMA_50': dma50,
                'DMA_100': dma100,
                'DMA_200': dma200,
                'exDividendDate': get_ex_dividend_date(symbol)
            })
        except Exception as e:
            print(f"Error fetching live stock for {symbol}: {e}")
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({})

@app.route('/')
def get_dma():
    # Authorization and Trial logic moved to Node Gateway (Render)
    response = {}
    try:
        stock = request.args.get('symbol')
        if not stock:
            return jsonify({"error": "Symbol parameter is required"}), 400
            
        dma_param = request.args.get('dma')
        if not dma_param:
            return jsonify({"error": "DMA parameter (comma-separated) is required"}), 400
            
        print(f"DEBUG: / (DMA) request for symbol: {stock}")
        dma_list = dma_param.split(',')
        today = datetime.now().date()
        from_date = today - timedelta(days=365)
        to_date = today + timedelta(days=1)
        df = custom_stock_df(symbol=stock, from_date=from_date, to_date=to_date, series="EQ")
        if df.empty:
            print(f"Skipping {stock}: No invalid historical data found.")
            return jsonify({})
            
        # Append live price to the end (CHRONOLOGICAL) if last row is older than today
        last_row_date = df.iloc[-1]['DATE']
        if isinstance(last_row_date, pd.Timestamp):
            last_row_date = last_row_date.date()
        elif isinstance(last_row_date, str):
            last_row_date = datetime.strptime(last_row_date.split(' ')[0], '%Y-%m-%d').date()

        if last_row_date < today:
            live_row = get_live_symbol_df(df.iloc[-1], stock, today)
            df = pd.concat([df, live_row], ignore_index=True)
        else:
            # Update today's existing bar with live price
            ticker_symbol = f"{stock}.NS"
            ticker = yf.Ticker(ticker_symbol)
            current_price = ticker.fast_info.last_price
            if current_price is None or pd.isna(current_price) or current_price == 0:
                current_price = ticker.info.get('currentPrice', df.iloc[-1]['CLOSE'])
            df.loc[df.index[-1], 'CLOSE'] = current_price
        
        rsi = TA.RSI(df)
        last_rsi = rsi.iloc[-1]
        
        response['symbol'] = stock
        response['id'] = stock
        response['price'] = df.iloc[-1]['CLOSE']
        response['rsi'] = round(float(last_rsi), 2) if not pd.isna(last_rsi) else None
        response['mcap'] = MCAP.get(stock, 0)
        response['name'] = COMPANY_NAME.get(stock, stock)
        response['volume'] = int(df.iloc[-1]['VOLUME']) if 'VOLUME' in df.columns else None
        response['url'] = 'https://www.screener.in/company/'+ stock +'/consolidated/'
        response['chart'] = 'https://in.tradingview.com/chart/?symbol=NSE%3A'+stock
        
        for item in dma_list:
            try:
                dema_series = TA.DEMA(df, int(item.split('_')[1]))
                last_dema = dema_series.iloc[-1]
                response[item] = round(float(last_dema), 2) if not pd.isna(last_dema) else None
            except Exception as e:
                print(f"Error calculating {item} for {stock}: {e}")
                response[item] = None

        # Safe bullish check (handle None)
        has_all_dmas = all(response.get(d) is not None for d in dma_list)
        if (response['rsi'] is not None and response['rsi'] > 20 and response['rsi'] < 70 
            and has_all_dmas and response['price'] > response.get('DMA_20', 0) 
            and response['price'] > response.get('DMA_50', 0) 
            and response['price'] > response.get('DMA_100', 0) 
            and response['price'] > response.get('DMA_200', 0)):
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
        
        # Calculate DEMA indicators for the history
        # We need enough data, ideally we download more than 'days' to have accurate DEMAs at the start
        df['dema20'] = TA.DEMA(df, 20)
        df['dema50'] = TA.DEMA(df, 50)
        df['dema100'] = TA.DEMA(df, 100)
        df['dema200'] = TA.DEMA(df, 200)
        
        # Format for frontend chart
        history_data = []
        for index, row in df.iterrows():
            history_data.append({
                'date': row['DATE'].strftime('%Y-%m-%d'),
                'price': row['CLOSE'],
                'dema20': row['dema20'] if not pd.isna(row['dema20']) else None,
                'dema50': row['dema50'] if not pd.isna(row['dema50']) else None,
                'dema100': row['dema100'] if not pd.isna(row['dema100']) else None,
                'dema200': row['dema200'] if not pd.isna(row['dema200']) else None,
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
    
    time_delta = int( request.args.get('timeDelta', 0 )) * TIME_DELTA
    today = (datetime.now() + timedelta(days=time_delta)).date()
    from_date = today - timedelta(days=365)
    to_date = today + timedelta(days=1)
    df = custom_stock_df(symbol=stock, from_date=from_date, to_date=to_date, series="EQ")
    if df.empty:
        print(f"Skipping {stock}: No invalid historical data found.")
        return jsonify({})
    
    # Append live price to the end (CHRONOLOGICAL) if last row is older than today
    last_row_date = df.iloc[-1]['DATE']
    if isinstance(last_row_date, pd.Timestamp):
        last_row_date = last_row_date.date()
    elif isinstance(last_row_date, str):
        last_row_date = datetime.strptime(last_row_date.split(' ')[0], '%Y-%m-%d').date()

    if last_row_date < today:
        live_row = get_live_symbol_df(df.iloc[-1], stock, today)
        df = pd.concat([df, live_row], ignore_index=True)
    else:
        # Update today's existing bar with live price
        ticker_symbol = f"{stock}.NS"
        ticker = yf.Ticker(ticker_symbol)
        current_price = ticker.fast_info.last_price
        if current_price is None or pd.isna(current_price) or current_price == 0:
            current_price = ticker.info.get('currentPrice', df.iloc[-1]['CLOSE'])
        df.loc[df.index[-1], 'CLOSE'] = current_price
    
    print(f"DEBUG: Processing {stock} | Price: {df.iloc[-1]['CLOSE']} | PriceDiff: {price_diff_val} | BearishDiff: {price_diff_bearish_val}")

    rsi = TA.RSI(df)
    last_rsi = rsi.iloc[-1]

    response['symbol'] = stock
    response['id'] = stock
    response['price'] = df.iloc[-1]['CLOSE']
    response['rsi'] = round(float(last_rsi), 2) if not pd.isna(last_rsi) else None
    
    mcap_val = MCAP.get(stock, 0)
    response['mcap'] = mcap_val
    response['name'] = COMPANY_NAME.get(stock, stock)
    response['industry'] = get_industry_with_fallback(stock)
    response['volume'] = int(df.iloc[-1]['VOLUME']) if 'VOLUME' in df.columns else None
    
    # Categorize Market Type based on MCAP (Cr)
    if mcap_val > 20000:
        response['marketType'] = 'Large Cap'
    elif mcap_val > 5000:
        response['marketType'] = 'Mid Cap'
    else:
        response['marketType'] = 'Small Cap'

    response['url'] = 'https://www.screener.in/company/'+ stock +'/consolidated/'
    response['chart'] = 'https://in.tradingview.com/chart/?symbol=NSE%3A'+stock
    
    for item in dma_list:
        try:
            dema_series = TA.DEMA(df, int(item.split('_')[1]))
            last_dema = dema_series.iloc[-1]
            response[item] = round(float(last_dema), 2) if not pd.isna(last_dema) else None
        except Exception as e:
            print(f"Error calculating {item} for {stock} in price_diff: {e}")
            response[item] = None
    
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

    # Bearish: Price well below DMAs (breakdown/extension)
    d20 = response.get('DMA_20')
    d50 = response.get('DMA_50')
    d100 = response.get('DMA_100')
    
    if (response['mcap'] > MCAP_THRESHOLD and 
        d20 and d50 and d100 and
        response['price'] < d20 and response['price'] < d50 and response['price'] < d100 and 
        abs(response['price'] - d20) > (response['price'] * price_diff_bearish_val) and 
        abs(d20 - d50) > (d20 * price_diff_bearish_val)):
        response['isBearish'] = 'true'
        print(f"MATCH BEARISH: {stock}")

    # --- Golden Cross Approach Detection ---
    # Detect stocks where DMA20 is converging toward DMA50 from below
    # (golden cross hasn't happened yet but is approaching)
    if dma50 > 0 and dma20 > 0 and price > 0:
        gap_20_50_pct = ((dma50 - dma20) / dma50) * 100  # positive = DMA20 below DMA50
        price_above_dma20_pct = ((price - dma20) / dma20) * 100

        response['goldenCrossGap'] = round(gap_20_50_pct, 3)

        # Golden cross approaching: DMA20 below DMA50, gap < 3%, price pushing above DMA20, RSI has room
        if (cond1  # mcap > threshold
            and dma20 > 0 and dma50 > 0 # ensure valid DMAs exist
            and dma20 < dma50  # hasn't crossed yet
            and gap_20_50_pct < 3  # close to crossing
            and price > dma20  # price momentum building
            and response['rsi'] is not None # handle None RSI
            and response['rsi'] > 35 and response['rsi'] < 65):  # not overbought, room to run
            response['isGoldenCrossApproaching'] = 'true'
            response['goldenCrossData'] = {
                'gap_pct': round(gap_20_50_pct, 3),
                'price_above_dma20_pct': round(price_above_dma20_pct, 2),
                'rsi': round(float(response['rsi']), 2)
            }
            print(f"MATCH GOLDEN CROSS APPROACHING: {stock} | Gap: {gap_20_50_pct:.3f}% | PriceAboveDMA20: {price_above_dma20_pct:.2f}%")

    return jsonify( response )

@app.route('/api/video/download/<filename>')
def download_video(filename):
    video_dir = os.path.join(os.path.dirname(__file__), 'temp_videos')
    return send_from_directory(video_dir, filename)

@app.route('/api/stocks/publish-video', methods=['POST'])
def publish_stock_video():
    data = request.get_json()
    symbol = data.get('symbol')
    platforms = data.get('platforms', ['telegram']) # default to telegram
    prompt = data.get('prompt')
    
    if not symbol or not prompt:
        return jsonify({"error": "Symbol and Prompt are required"}), 400

    # Start the async publishing flow in a background thread
    def run_publish_flow():
        try:
            print(f"[Publish Flow] Starting flow for {symbol}...")
            config = load_config()
            
            # 1. Generate Video via VEO
            generator = VeoVideoGenerator()
            video_filename = generator.generate(prompt, symbol)
            
            if not video_filename:
                print(f"[Publish Flow] Failed to generate video for {symbol}")
                return

            video_path = os.path.join(os.path.dirname(__file__), 'temp_videos', video_filename)
            # Ensure the relative path is correct for the public URL
            base_url = config.get('currentTunnelUrl', 'http://localhost:5000').rstrip('/')
            public_url = f"{base_url}/api/video/download/{video_filename}"
            
            print(f"[Publish Flow] Video generated: {video_filename}")
            print(f"[Publish Flow] Public URL: {public_url}")
            
            caption = f"📈 {symbol} Analysis\n\n{prompt.split('.')[-1].strip()}"

            # 2. Publish to Telegram
            print(f"[Publish Flow] Broadcasting analysis to Telegram...")
            tg = TelegramPublisher()
            tg.publish(public_url, caption)
            
            print(f"[Publish Flow] Flow completed for {symbol}")
        except Exception as e:
            print(f"[Publish Flow Error] {e}")

    threading.Thread(target=run_publish_flow).start()
    return jsonify({"status": "queued", "message": "Video generation and publishing started in background"}), 202

@app.route('/api/global-cues')
@cache_endpoint(ttl_seconds=86400)
def get_global_cues():
    try:
        from market_intelligence import fetch_global_cues
        cues = fetch_global_cues()
        return jsonify({"cues": cues})
    except Exception as e:
        print(f"Error in /api/global-cues: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/earnings-calendar')
@cache_endpoint(ttl_seconds=86400)
def get_earnings_calendar_route():
    try:
        from market_intelligence import get_earnings_calendar
        # Get symbols from request or default to top
        symbols = request.args.get('symbols')
        if symbols:
            symbols = symbols.split(',')
        
        calendar = get_earnings_calendar(symbols)
        return jsonify({"calendar": calendar})
    except Exception as e:
        print(f"Error in /api/earnings-calendar: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    port = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PORT', 5001)
    serve(app, host='0.0.0.0', port=int(port), threads=4)
