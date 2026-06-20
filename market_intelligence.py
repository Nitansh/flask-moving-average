import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
from bs4 import BeautifulSoup

# Load MCAP data to identify top stocks
try:
    from mcap import MCAP, COMPANY_NAME
except ImportError:
    MCAP = {}
    COMPANY_NAME = {}

def get_top_stocks(limit=100):
    """Get top stocks by market cap."""
    sorted_stocks = sorted(MCAP.items(), key=lambda x: x[1], reverse=True)
    return [s[0] for s in sorted_stocks[:limit]]

def fetch_global_cues():
    """Fetch recent global and domestic financial news."""
    url = "https://news.google.com/rss/search?q=NSE+India+market+macroeconomics+global+events&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, features="xml")
        items = soup.find_all('item')
        news_list = []
        for item in items[:20]:  # Take top 20 news items
            news_list.append({
                'title': item.title.text,
                'link': item.link.text,
                'pubDate': item.pubDate.text,
                'source': item.source.text if item.source else 'Google News'
            })
        return news_list
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

EARNINGS_CACHE_FILE = 'earnings_calendar_cache.json'
EARNINGS_CACHE_LOCK = threading.Lock()
EARNINGS_CACHE_TTL = 24 * 60 * 60  # Cache for 24 hours

def load_earnings_cache():
    if os.path.exists(EARNINGS_CACHE_FILE):
        try:
            with open(EARNINGS_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading earnings cache: {e}")
    return {'data': None, 'timestamp': 0}

def save_earnings_cache(cache_data):
    try:
        with open(EARNINGS_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
    except Exception as e:
        print(f"Error saving earnings cache: {e}")

def fetch_single_ticker_calendar(symbol, today, next_30_days):
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        cal = ticker.calendar
        results = []
        if cal and 'Earnings Date' in cal:
            earnings_dates = cal['Earnings Date']
            for e_date in earnings_dates:
                if not isinstance(e_date, datetime):
                    e_date = datetime.combine(e_date, datetime.min.time())
                
                if today.date() <= e_date.date() <= next_30_days.date():
                    results.append({
                        'symbol': symbol,
                        'company': COMPANY_NAME.get(symbol, symbol),
                        'date': e_date.strftime('%Y-%m-%d'),
                        'eps_est': cal.get('Earnings Average', 'N/A'),
                        'rev_est': cal.get('Revenue Average', 'N/A'),
                        'sentiment': 'Neutral'
                    })
        return results
    except:
        return []

def get_earnings_calendar(stocks=None):
    """Fetch earnings calendar for a list of stocks or top stocks."""
    
    # Only use cache when querying default top stocks (no custom stocks filter)
    if not stocks:
        current_time = time.time()
        with EARNINGS_CACHE_LOCK:
            cache = load_earnings_cache()
            if cache['data'] is not None and (current_time - cache['timestamp'] < EARNINGS_CACHE_TTL):
                print("[EARNINGS CACHE HIT] Using cached earnings calendar")
                return cache['data']
        
        stocks = get_top_stocks(150)
        is_default_query = True
    else:
        is_default_query = False

    print(f"[EARNINGS FETCH] Fetching earnings calendar concurrently for {len(stocks)} stocks...")
    calendar = []
    today = datetime.now()
    next_30_days = today + timedelta(days=30)
    
    # Query yfinance concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=15) as executor: # Reduced max_workers to avoid aggressive rate limiting
        future_to_symbol = {
            executor.submit(fetch_single_ticker_calendar, symbol, today, next_30_days): symbol 
            for symbol in stocks
        }
        
        for future in as_completed(future_to_symbol):
            try:
                res = future.result()
                if res:
                    calendar.extend(res)
            except:
                pass
                
    # Sort by date
    calendar.sort(key=lambda x: x['date'])
    
    # Save to cache if it was the default query
    if is_default_query:
        with EARNINGS_CACHE_LOCK:
            # If the fetch returned absolutely nothing (e.g. rate-limited), fallback to existing cache data if available
            old_cache = load_earnings_cache()
            if not calendar and old_cache['data']:
                print("[EARNINGS FETCH FAILED] Yahoo Finance rate-limited or failed. Falling back to stale cache.")
                return old_cache['data']
                
            cache_data = {
                'data': calendar,
                'timestamp': current_time
            }
            save_earnings_cache(cache_data)
            print(f"[EARNINGS CACHE] Saved {len(calendar)} calendar items to cache.")
            
    return calendar
