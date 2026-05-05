import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

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

def fetch_financial_news():
    """Fetch recent financial news related to NSE and macroeconomics."""
    url = "https://news.google.com/rss/search?q=NSE+India+market+macroeconomics+global+events&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, features="xml")
        items = soup.find_all('item')
        news_list = []
        for item in items[:15]:  # Take top 15 news items
            news_list.append({
                'title': item.title.text,
                'link': item.link.text,
                'pubDate': item.pubDate.text
            })
        return news_list
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []

def get_earnings_calendar(stocks):
    """Fetch earnings calendar for a list of stocks."""
    calendar = []
    today = datetime.now()
    next_15_days = today + timedelta(days=15)
    
    for symbol in stocks:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            cal = ticker.calendar
            if cal and 'Earnings Date' in cal:
                # Earnings Date can be a list of dates
                earnings_dates = cal['Earnings Date']
                for e_date in earnings_dates:
                    # Convert to datetime if it's not
                    if not isinstance(e_date, datetime):
                        e_date = datetime.combine(e_date, datetime.min.time())
                    
                    if today <= e_date <= next_15_days:
                        calendar.append({
                            'symbol': symbol,
                            'company': COMPANY_NAME.get(symbol, symbol),
                            'date': e_date.strftime('%Y-%m-%d'),
                            'eps_est': cal.get('Earnings Average', 'Data Not Available'),
                            'rev_est': cal.get('Revenue Average', 'Data Not Available')
                        })
        except Exception as e:
            # print(f"Error fetching calendar for {symbol}: {e}")
            pass
    return calendar

def generate_market_intelligence(api_key):
    """Use Gemini to generate market intelligence report."""
    client = genai.Client(api_key=api_key)
    
    news = fetch_financial_news()
    top_stocks = get_top_stocks(50)  # Use top 50 for performance
    earnings = get_earnings_calendar(top_stocks)
    
    news_context = "\n".join([f"- {n['title']} ({n['pubDate']})" for n in news])
    earnings_context = json.dumps(earnings, indent=2)
    
    prompt = f"""
You are an advanced financial market intelligence AI focused on identifying stock opportunities in NSE (National Stock Exchange of India).

CONTEXT:
Current Global/Domestic News:
{news_context}

Upcoming Earnings Data (Next 15 Days):
{earnings_context}

YOUR TASK:
Analyze the above context and generate a detailed report following the strict output format below.

Output Format (Strict)
Section 1: Global Event Driven Opportunities
Event: [Event Name]
Stock: [Stock Name]
Insight: Due to [Event], [Stock] is likely to [Rise/Fall] because [Reason]
Impact: [Bullish/Bearish/Neutral]
Confidence: [High/Medium/Low]
Time Horizon: [Intraday/Short-term/Medium-term]

Section 2: Earnings Calendar (Next 15 Days)
Date: [DD-MM-YYYY]
[Company Name]
Sector: 
Estimated EPS: 
Previous EPS: 
Expected Revenue: 
Previous Revenue: 
Sentiment: 
Volatility Expectation: 

Section 3: Post-Result Updates (if applicable)
[Company Name]
Actual EPS vs Expected: 
Actual Revenue vs Expected: 
Result: Beat / Inline / Miss
Market Reaction Bias: 

Section 4: Combined Insights
[Company Name]: "Due to [Event] and upcoming results on [Date], the stock is likely to [Outcome] because [Reason]."

Rules:
1. Focus only on NSE-listed stocks.
2. Avoid generic statements; provide clear cause-effect reasoning.
3. Do not include technical indicators (RSI, DMA).
4. Prioritize clarity and actionable insights.
5. Do not hallucinate unknown data; mark unavailable fields as "Data Not Available".
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error generating intelligence: {str(e)}"

if __name__ == "__main__":
    # Test execution
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        print(generate_market_intelligence(api_key))
    else:
        print("GOOGLE_API_KEY not found in environment.")
