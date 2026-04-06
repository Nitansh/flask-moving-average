import asyncio
import httpx
import json
from mcp.server.fastmcp import FastMCP

# Create a FastMCP server named "MarketAnalysis"
mcp = FastMCP("MarketAnalysis")

# Configuration for local service endpoints
BALANCER_URL = "http://localhost:4001"
MANAGER_URL = "http://localhost:8081"
GATEWAY_URL = "https://movingaverage-sh7s.onrender.com/"

@mcp.tool()
async def get_stock_analysis(symbol: str) -> str:
    """
    Fetch comprehensive technical analysis for an NSE stock.
    Returns: Price, RSI, DEMA 20/50/100/200, and trend flags (Bullish/Bearish).
    """
    symbol = symbol.upper().replace(".NS", "")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {
                "symbol": symbol,
                "dma": "20,50,100,200",
                "priceDiff": 3,
                "priceDiffBullish": 5
            }
            response = await client.get(f"{BALANCER_URL}/price_diff", params=params)
            response.raise_for_status()
            data = response.json()
            return json.dumps(data, indent=2)
    except Exception as e:
        return f"Error fetching analysis for {symbol}: {str(e)}"

@mcp.tool()
async def save_stock_data(symbol: str, quantity: int, price: float) -> str:
    """
    Save or Update a stock in your persistent portfolio.
    If quantity is 0, the stock is automatically moved to your Watchlist.
    """
    symbol = symbol.upper().replace(".NS", "")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if quantity == 0:
                await client.post(f"{GATEWAY_URL}/api/watchlist", json={"symbol": symbol})
                await client.post(f"{GATEWAY_URL}/api/portfolio", json={"symbol": symbol, "quantity": 0})
                return f"Stock {symbol} moved to Watchlist (Quantity set to 0)."
            else:
                response = await client.post(f"{GATEWAY_URL}/api/portfolio", json={
                    "symbol": symbol,
                    "quantity": int(quantity),
                    "price": float(price)
                })
                response.raise_for_status()
                return f"Stock {symbol} saved to Portfolio: {quantity} shares @ ₹{price}."
    except Exception as e:
        return f"Error saving stock data: {str(e)}"

@mcp.tool()
async def remove_from_watchlist(symbol: str) -> str:
    """
    Remove a stock from your persistent watchlist.
    """
    symbol = symbol.upper().replace(".NS", "")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{GATEWAY_URL}/api/watchlist/{symbol}")
            response.raise_for_status()
            return f"Stock {symbol} removed from Watchlist."
    except Exception as e:
        return f"Error removing from watchlist: {str(e)}"

@mcp.tool()
async def view_full_portfolio() -> str:
    """
    View your entire portfolio with live technical indicators (Price, RSI, DEMA, P&L).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{GATEWAY_URL}/api/portfolio")
            holdings = resp.json()
            if not holdings: return "Your portfolio is currently empty."
            enriched_holdings = []
            for item in holdings:
                try:
                    analysis_resp = await client.get(f"{BALANCER_URL}/price_diff", params={"symbol": item['symbol'], "dma": "20,50,100,200"})
                    tech = analysis_resp.json()
                    current_price = tech.get('price', 0)
                    pnl = (current_price - item['price']) * item['quantity']
                    pnl_pct = ((current_price - item['price']) / item['price']) * 100 if item['price'] > 0 else 0
                    enriched_holdings.append({
                        "Symbol": item['symbol'], "Qty": item['quantity'], "AvgPrice": item['price'],
                        "LTP": round(current_price, 2), "P&L": round(pnl, 2), "P&L%": round(pnl_pct, 2),
                        "RSI": round(tech.get('rsi', 0), 1), "DMA_20": round(tech.get('DMA_20', 0), 2),
                        "DMA_50": round(tech.get('DMA_50', 0), 2),
                        "Trend": "Bullish" if tech.get('isBullish') == 'true' else "Bearish" if tech.get('isBearish') == 'true' else "Neutral"
                    })
                except: enriched_holdings.append({**item, "status": "Tech fetch failed"})
            return json.dumps(enriched_holdings, indent=2)
    except Exception as e: return f"Error viewing portfolio: {str(e)}"

@mcp.tool()
async def view_full_watchlist() -> str:
    """
    View your full watchlist with live technical metrics.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{GATEWAY_URL}/api/watchlist")
            items = resp.json()
            if not items: return "Your watchlist is empty."
            enriched_items = []
            for item in items:
                try:
                    analysis_resp = await client.get(f"{BALANCER_URL}/price_diff", params={"symbol": item['symbol'], "dma": "20,50,100,200"})
                    tech = analysis_resp.json()
                    enriched_items.append({
                        "Symbol": item['symbol'], "LTP": round(tech.get('price', 0), 2),
                        "RSI": round(tech.get('rsi', 0), 1), "DMA_20": round(tech.get('DMA_20', 0), 2),
                        "DMA_50": round(tech.get('DMA_50', 0), 2), "AddedOn": item.get('date')
                    })
                except: enriched_items.append({**item, "status": "Tech fetch failed"})
            return json.dumps(enriched_items, indent=2)
    except Exception as e: return f"Error viewing watchlist: {str(e)}"

@mcp.tool()
async def get_bullish_stocks() -> str:
    """Get the latest list of bullish stocks."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GATEWAY_URL}/api/bullish-list")
            return json.dumps(response.json(), indent=2)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
async def get_bearish_stocks() -> str:
    """Get the latest list of bearish stocks."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GATEWAY_URL}/api/bearish-list")
            return json.dumps(response.json(), indent=2)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
async def get_sniper_picks() -> str:
    """Identify 'Sniper' entries (Price within 1.5% of DMA 20)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GATEWAY_URL}/api/full-list")
            full_list = response.json()
            sniper_picks = []
            for s in full_list:
                if s.get('isBullish') == 'true':
                    price, dma20 = s.get('price', 0), s.get('DMA_20', 0)
                    if dma20 > 0 and abs(price - dma20) / dma20 * 100 < 1.5:
                        s['sniper_gap'] = round(abs(price - dma20) / dma20 * 100, 2)
                        sniper_picks.append(s)
            return json.dumps(sniper_picks, indent=2)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
async def check_infra_status() -> str:
    """Check system health status."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MANAGER_URL}/api/system/status")
            return json.dumps(response.json(), indent=2)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
async def restart_infrastructure() -> str:
    """Global restart of all backend services."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{MANAGER_URL}/api/system/restart/all")
            return json.dumps(response.json(), indent=2)
    except Exception as e: return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()
