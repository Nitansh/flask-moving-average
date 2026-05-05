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

def get_earnings_calendar(stocks=None):
    """Fetch earnings calendar for a list of stocks or top stocks."""
    if not stocks:
        stocks = get_top_stocks(150)  # Scan top 150 stocks for earnings
        
    calendar = []
    today = datetime.now()
    next_30_days = today + timedelta(days=30) # Expand to 30 days for better coverage
    
    # Use a thread pool or simple loop for now
    for symbol in stocks:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            cal = ticker.calendar
            if cal and 'Earnings Date' in cal:
                earnings_dates = cal['Earnings Date']
                for e_date in earnings_dates:
                    if not isinstance(e_date, datetime):
                        e_date = datetime.combine(e_date, datetime.min.time())
                    
                    if today.date() <= e_date.date() <= next_30_days.date():
                        calendar.append({
                            'symbol': symbol,
                            'company': COMPANY_NAME.get(symbol, symbol),
                            'date': e_date.strftime('%Y-%m-%d'),
                            'eps_est': cal.get('Earnings Average', 'N/A'),
                            'rev_est': cal.get('Revenue Average', 'N/A'),
                            'sentiment': 'Neutral' # Default since we removed AI
                        })
        except:
            pass
            
    # Sort by date
    calendar.sort(key=lambda x: x['date'])
    return calendar
