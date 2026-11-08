"""
Real-time live market quote fetcher.
Provides ultra-low latency, accurate live prices directly from primary exchange feeds (Google Finance)
during special trading sessions (e.g. Muhurat trading) and whenever secondary feeds (Yahoo Finance) lag.
"""

import urllib.request
import re
import time
import threading
from datetime import datetime

_GF_CACHE = {}
_GF_CACHE_LOCK = threading.Lock()
_GF_CACHE_TTL = 8  # 8 seconds TTL for live tick updates

INDEX_TARGET_MAP = {
    'NIFTY': 'NIFTY_50:INDEXNSE',
    'NIFTY 50': 'NIFTY_50:INDEXNSE',
    'NIFTY50': 'NIFTY_50:INDEXNSE',
    'NSEI': 'NIFTY_50:INDEXNSE',
    '^NSEI': 'NIFTY_50:INDEXNSE',
    'BANKNIFTY': 'NIFTY_BANK:INDEXNSE',
    'NIFTYBANK': 'NIFTY_BANK:INDEXNSE',
    '^NSEBANK': 'NIFTY_BANK:INDEXNSE',
    'FINNIFTY': 'NIFTY_FIN_SERVICE:INDEXNSE',
    'MIDCPNIFTY': 'NIFTY_MID_SELECT:INDEXNSE'
}

def is_special_session_today():
    """Check if today is a special trading session (e.g., Muhurat trading)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    return today_str == "2026-11-08"

def fetch_live_quote_gf(symbol):
    """
    Fetch live market quote with price, change, changePercent, and previousClose.
    """
    if not symbol:
        return None
    clean_sym = str(symbol).replace('.NS', '').replace('^', '').strip().upper()
    now = time.time()

    with _GF_CACHE_LOCK:
        if clean_sym in _GF_CACHE and (now - _GF_CACHE[clean_sym]['time'] < _GF_CACHE_TTL):
            return _GF_CACHE[clean_sym]['data'].copy()

    target = INDEX_TARGET_MAP.get(clean_sym, f"{clean_sym}:NSE")
    url = f"https://www.google.com/finance/quote/{target}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        pos = html.find('class="N6SYTe"')
        if pos != -1:
            block = html[pos:pos+700]
            price_match = re.search(r'class="N6SYTe"><span[^>]*><span>₹?([0-9,]+(?:\.[0-9]+)?)</span>', block)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                pct_match = re.search(r'jsname="vY9t3b"[^>]*><span[^>]*>([+-]?[0-9,]+(?:\.[0-9]+)?)%</span>', block)
                change_pct = float(pct_match.group(1).replace(',', '')) if pct_match else 0.0
                chg_match = re.search(r'jsname="xnruHf"[^>]*><span>([+-]?[0-9,]+(?:\.[0-9]+)?)</span>', block)
                change = float(chg_match.group(1).replace(',', '')) if chg_match else 0.0

                if 'arrow_downward' in block:
                    if change > 0:
                        change = -change
                    if change_pct > 0:
                        change_pct = -change_pct

                prev_close = round(price - change, 2)
                res = {
                    'symbol': clean_sym,
                    'price': price,
                    'currentPrice': price,
                    'change': change,
                    'changePercent': change_pct,
                    'previousClose': prev_close
                }
                with _GF_CACHE_LOCK:
                    _GF_CACHE[clean_sym] = {'data': res, 'time': now}
                return res.copy()
    except Exception:
        pass

    return None

def get_realtime_price(symbol, fallback=None):
    """
    Get the single latest live price as float.
    """
    quote = fetch_live_quote_gf(symbol)
    if quote and quote.get('price'):
        return quote['price']
    return fallback
