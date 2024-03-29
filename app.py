from flask import Flask, jsonify, request
from datetime import date, timedelta, datetime
from jugaad_data.nse import stock_df, NSELive
from finta import TA
from waitress import serve
import pandas as pd
import sys

from mcap import MCAP, COMPANY_NAME

app = Flask(__name__)
n = NSELive()
pd.options.mode.copy_on_write = True

PRICE_DIFF_PERCENTAGE = 1
PRICE_DIFF_BEARISH_PERCENTAGE = 5
MCAP_THRESHOLD = 10
TIME_DELTA = -1


def get_live_symbol_df( df ):
    try:
        stockData = n.stock_quote(df['SYMBOL'])
        df['DATE'] = df['DATE']+ timedelta(days=1)
        df['OPEN'] = stockData['priceInfo']['open']
        df['PREV. CLOSE'] = df['CLOSE']
        df['LTP'] = stockData['priceInfo']['lastPrice']
        df['CLOSE'] = stockData['priceInfo']['lastPrice']
        df['VWAP'] = stockData['priceInfo']['vwap']
    except:
        pass
    return df

@app.route('/healthcheck')
def get_healt_check():
    print("in Health Check")
    df = stock_df(symbol='RELIANCE', from_date=date(2022,7,12), to_date=date(2023,7,12), series="EQ")
    return 'working'

@app.route('/live')
def get_live_stock():
    symbol = request.args.get('symbol')
    if ( symbol ):
        stockData = n.stock_quote(symbol)
        return jsonify({
            'symbol' : symbol,
            'industry' : stockData.get('info').get('industry'),
            'currentPrice' : stockData['priceInfo']['lastPrice']
        })
    else:
        return jsonify({})

@app.route('/')
def get_dma():
    response = {}
    try:
        stock = request.args.get('symbol')
        dma_list = request.args.get('dma').split(',')
        one_day_before = datetime.now() + timedelta(days=-1)
        year = one_day_before.year
        month = one_day_before.month
        day = one_day_before.day
        df = stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
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
        for item in dma_list:
            response[item] = TA.DEMA(df, int(item.split('_')[1] ) ).iloc[-1]
        if response['rsi'] > 20 and response['rsi'] < 70 and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50'] and response['price'] > response['DMA_100'] and response['price'] > response['DMA_200']:
            response['isBullish'] = 'true'
    except:
        print( "Error occurred in "+stock)

    return jsonify( response )


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
    df = stock_df(symbol=stock, from_date=date(year-1,month,day), to_date=date(year,month,day), series="EQ")
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
