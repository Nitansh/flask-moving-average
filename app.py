from flask import Flask, jsonify, request
from datetime import date
from jugaad_data.nse import stock_csv, stock_df
from finta import TA
from waitress import serve

app = Flask(__name__)


@app.route('/healthcheck')
def get_healt_check():
    print("in Health Check")
    df = stock_df(symbol='RELIANCE', from_date=date(2022,7,12), to_date=date(2023,7,12), series="EQ")
    return ''


@app.route('/')
def get_dma():
    response = {}
    stock = request.args.get('symbol')
    dma_list = request.args.get('dma').split(',')
    df = stock_df(symbol=stock, from_date=date(2022,7,12), to_date=date(2023,7,12), series="EQ")
    df = df.iloc[::-1]
    rsi = TA.RSI(df)
    
    response['symbol'] = stock
    response['price'] = df.iloc[-1]['CLOSE']
    response['rsi'] = rsi.iloc[-1]
    for item in dma_list:
        response[item] = TA.DEMA(df, int(item.split('_')[1] ) ).iloc[-1]
    if response['rsi'] > 30 and response['rsi'] < 70 and response['price'] > response['DMA_20'] and response['price'] > response['DMA_50'] and response['price'] > response['DMA_100'] and response['price'] > response['DMA_200']:
        response['isBullish'] = 'true'

    return jsonify( response )
    
if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=5000)
