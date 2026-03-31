from flask import Flask, jsonify, request, send_from_directory
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
from publish_service import VeoVideoGenerator, InstagramPublisher, TelegramPublisher, load_config
import asyncio
import threading
from flask_cors import CORS
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
        
        df['SYMBOL'] = symbol
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

def get_live_symbol_df(last_row, symbol):
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

        # Convert Series to dict
        row_dict = last_row.to_dict()

        # Modify values
        row_dict['DATE'] = row_dict['DATE'] + timedelta(days=1)
        row_dict['OPEN'] = open_price
        row_dict['PREV. CLOSE'] = row_dict['CLOSE']
        row_dict['LTP'] = last_price
        row_dict['CLOSE'] = last_price
        row_dict['VWAP'] = last_price

        # Return proper DataFrame
        return pd.DataFrame([row_dict])

    except Exception as e:
        print(f"Error in get_live_symbol_df: {e}")
        return pd.DataFrame()

@app.route('/healthcheck')
def get_health_check():
    # Performance deep-health: Fetch live data for RELIANCE to verify whole pipeline
    try:
        ticker = yf.Ticker('RELIANCE.NS')
        current_price = ticker.fast_info.last_price
        if current_price and current_price > 0:
            return jsonify({
                "status": "healthy",
                "verification": {
                    "symbol": "RELIANCE.NS",
                    "price": current_price,
                    "timestamp": datetime.now().isoformat()
                }
            }), 200
        else:
            return jsonify({"status": "degraded", "error": "Invalid price data from Yahoo"}), 502
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 503

@app.route('/live')
def get_live_stock():
    symbol = request.args.get('symbol')
    print(f"DEBUG: /live request for symbol: {symbol}")
    if ( symbol ):
        try:
            ticker_symbol = f"{symbol}.NS"
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            
            return jsonify({
                'symbol' : symbol,
                'industry' : info.get('industry', 'N/A'),
                'currentPrice' : info.get('currentPrice', info.get('regularMarketPrice', 0))
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
        print(f"DEBUG: / (DMA) request for symbol: {stock}")
        dma_list = request.args.get('dma').split(',')
        one_day_before = datetime.now() + timedelta(days=-1)
        year = one_day_before.year
        month = one_day_before.month
        day = one_day_before.day
        df = custom_stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
        if df.empty:
            print(f"Skipping {stock}: No invalid historical data found.")
            return jsonify({})
            
        df = df.iloc[::-1]
        
        # Double check if reversal made it empty (unlikely but safe)
        if df.empty:
            return jsonify({})
        live_row = get_live_symbol_df(df.iloc[0], stock)   
        df = pd.concat([df, live_row], ignore_index=True)
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
    
    time_delta = int( request.args.get('timeDelta', 0 )) * TIME_DELTA
    one_day_before = datetime.now() + timedelta(days=time_delta)
    year = one_day_before.year
    month = one_day_before.month
    day = one_day_before.day
    df = custom_stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
    if df.empty:
        print(f"Skipping {stock}: No invalid historical data found.")
        return jsonify({})

    df = df.iloc[::-1]
    live_row = get_live_symbol_df(df.iloc[0],stock)
    df = pd.concat([df,live_row], ignore_index=True)
    
    print(f"DEBUG: Processing {stock} | Price: {df.iloc[-1]['CLOSE']} | PriceDiff: {price_diff_val} | BearishDiff: {price_diff_bearish_val}")

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

    # --- Golden Cross Approach Detection ---
    # Detect stocks where DMA20 is converging toward DMA50 from below
    # (golden cross hasn't happened yet but is approaching)
    if dma50 > 0 and dma20 > 0 and price > 0:
        gap_20_50_pct = ((dma50 - dma20) / dma50) * 100  # positive = DMA20 below DMA50
        price_above_dma20_pct = ((price - dma20) / dma20) * 100

        response['goldenCrossGap'] = round(gap_20_50_pct, 3)

        # Golden cross approaching: DMA20 below DMA50, gap < 3%, price pushing above DMA20, RSI has room
        if (cond1  # mcap > threshold
            and dma20 < dma50  # hasn't crossed yet
            and gap_20_50_pct < 3  # close to crossing
            and price > dma20  # price momentum building
            and response['rsi'] > 35 and response['rsi'] < 65):  # not overbought, room to run
            response['isGoldenCrossApproaching'] = 'true'
            response['goldenCrossData'] = {
                'gap_pct': round(gap_20_50_pct, 3),
                'price_above_dma20_pct': round(price_above_dma20_pct, 2),
                'rsi': round(response['rsi'], 2)
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

            # 2. Publish to selected platforms
            if not platforms or 'none' in platforms:
                print(f"[Publish Flow] Video generation complete for {symbol}. No platforms selected.")
                return

            if 'instagram' in platforms:
                print(f"[Publish Flow] Publishing to Instagram...")
                ig_conf = config.get('instagram', {})
                if ig_conf.get('access_token'):
                    ig = InstagramPublisher(ig_conf['access_token'], ig_conf['user_id'])
                    ig.publish(public_url, caption)
                else:
                    print("[Publish Flow] Instagram credentials missing.")
                    
            if 'telegram' in platforms:
                print(f"[Publish Flow] Publishing to Telegram...")
                tg_conf = config.get('telegram', {})
                if tg_conf.get('bot_token'):
                    tg = TelegramPublisher(tg_conf['bot_token'], tg_conf['chat_id'])
                    asyncio.run(tg.publish(video_path, caption))
                else:
                    print("[Publish Flow] Telegram credentials missing.")
            
            print(f"[Publish Flow] Flow completed for {symbol}")
        except Exception as e:
            print(f"[Publish Flow Error] {e}")

    threading.Thread(target=run_publish_flow).start()
    return jsonify({"status": "queued", "message": "Video generation and publishing started in background"}), 202

if __name__ == '__main__':
    port = sys.argv[1]
    # host='::' for dual-stack + threads=4 for concurrent stock fetches
    serve(app, host='::', port=port, threads=4)
