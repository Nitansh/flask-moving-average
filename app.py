from flask import Flask, jsonify, request
from datetime import date, timedelta, datetime
from jugaad_data.nse import NSELive
from jugaad_data.nse.history import NSEHistory, stock_select_headers, stock_final_headers, stock_dtypes
from finta import TA
from waitress import serve
import pandas as pd
import sys
import requests

from mcap import MCAP, COMPANY_NAME

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
        
        self.s = requests.Session()
        h = {
            "Host": "www.nseindia.com",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=INFY",
            "X-Requested-With": "XMLHttpRequest",
            "pragma": "no-cache",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7,hi;q=0.6",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "priority": "u=0, i",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        self.s.headers.update(h)
        self.s.get(self.page_url)

class CustomNSEHistory(NSEHistory):
    def __init__(self):
        # Call parent init first to get all methods
        super().__init__()
        # Now override headers with our custom ones
        self.headers = {
            "Host": "www.nseindia.com",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=INFY",
            "X-Requested-With": "XMLHttpRequest",
            "pragma": "no-cache",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7,hi;q=0.6",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "priority": "u=0, i",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        # Update session headers
        self.s.headers.update(self.headers)

def custom_stock_df(symbol, from_date, to_date, series="EQ"):
    h = CustomNSEHistory()
    raw = h.stock_raw(symbol, from_date, to_date, series)
    df = pd.DataFrame(raw)[stock_select_headers]
    df.columns = stock_final_headers
    for i, h in enumerate(stock_final_headers):
        df[h] = df[h].apply(stock_dtypes[i])
    return df

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
    price_diff = int( request.args.get('priceDiff', PRICE_DIFF_PERCENTAGE ) ) * .001 
    price_diff_bearish = int( request.args.get('priceDiffBullish', PRICE_DIFF_BEARISH_PERCENTAGE )) *.01
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
    if response['mcap'] > MCAP_THRESHOLD and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50']  and response['price'] > response['DMA_100']  and abs(response['DMA_20'] - response['DMA_50']) < (response['price'] * price_diff) and abs(response['DMA_50'] - response['DMA_100']) < (response['price'] * price_diff):
        response['isBullish'] = 'true'

    if response['mcap'] > MCAP_THRESHOLD and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50']  and response['price'] > response['DMA_100']  and abs(response['price'] - response['DMA_20']) > (response['price'] * price_diff_bearish) and abs(response['DMA_20'] - response['DMA_50']) > (response['DMA_20'] * price_diff_bearish):
        response['isBearish'] = 'true'

    return jsonify( response )
    
if __name__ == '__main__':
    port = sys.argv[1]
    serve(app, host='0.0.0.0', port=port)
