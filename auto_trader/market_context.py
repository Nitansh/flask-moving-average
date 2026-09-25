"""
Market Context & Technical Indicator Helpers for Auto-Trader
Fetches and caches NIFTY 50 benchmark prices and DEMAs (20, 50, 100, 200),
and extracts technical indicators (RSI, Volume, DEMAs) for trade logging and algo analytics.
"""
import time
import pandas as pd
from finta import TA
import yfinance as yf

_NIFTY_CACHE = {
    "timestamp": 0.0,
    "data": {
        "nifty_price": None,
        "nifty_dema_20": None,
        "nifty_dema_50": None,
        "nifty_dema_100": None,
        "nifty_dema_200": None
    }
}

def get_nifty_market_context(force_refresh=False, max_age_seconds=120):
    """
    Returns live or cached NIFTY 50 benchmark price and DEMAs (20, 50, 100, 200).
    Caches results for max_age_seconds to ensure rapid execution during multi-stock evaluation.
    """
    now = time.time()
    if not force_refresh and _NIFTY_CACHE["data"]["nifty_price"] is not None:
        if (now - _NIFTY_CACHE["timestamp"]) < max_age_seconds:
            return _NIFTY_CACHE["data"]

    try:
        ticker = yf.Ticker("^NSEI")
        fast_info = getattr(ticker, "fast_info", None)
        price = None
        if fast_info:
            try:
                price = fast_info.last_price
            except Exception:
                pass

        hist = ticker.history(period="1y")
        if hist.empty:
            return _NIFTY_CACHE["data"]

        if price is None or pd.isna(price) or price <= 0:
            price = hist["Close"].iloc[-1]

        # Update last close in hist with live price for real-time DEMA calculation
        if price and not pd.isna(price):
            hist.loc[hist.index[-1], "Close"] = float(price)

        d20, d50, d100, d200 = None, None, None, None
        try:
            if len(hist) >= 20:
                s20 = TA.DEMA(hist, 20)
                d20 = round(float(s20.iloc[-1]), 2) if not pd.isna(s20.iloc[-1]) else None
            if len(hist) >= 50:
                s50 = TA.DEMA(hist, 50)
                d50 = round(float(s50.iloc[-1]), 2) if not pd.isna(s50.iloc[-1]) else None
            if len(hist) >= 100:
                s100 = TA.DEMA(hist, 100)
                d100 = round(float(s100.iloc[-1]), 2) if not pd.isna(s100.iloc[-1]) else None
            if len(hist) >= 200:
                s200 = TA.DEMA(hist, 200)
                d200 = round(float(s200.iloc[-1]), 2) if not pd.isna(s200.iloc[-1]) else None
        except Exception as dema_err:
            print(f"Warning: error calculating Nifty DEMAs: {dema_err}")

        res = {
            "nifty_price": round(float(price), 2) if (price and not pd.isna(price)) else None,
            "nifty_dema_20": d20,
            "nifty_dema_50": d50,
            "nifty_dema_100": d100,
            "nifty_dema_200": d200
        }
        _NIFTY_CACHE["timestamp"] = now
        _NIFTY_CACHE["data"] = res
        return res
    except Exception as ex:
        print(f"Warning: Failed to fetch NIFTY market context: {ex}")
        return _NIFTY_CACHE["data"]

def extract_indicators_dict(stock_or_pos=None, dema_data=None, extra_rsi=None, extra_volume=None):
    """
    Extracts stock technical indicators (RSI, volume, DEMAs) and enriches with NIFTY market context.
    """
    stock_or_pos = stock_or_pos or {}
    dema_data = dema_data or {}

    def _val(*keys):
        for k in keys:
            v = stock_or_pos.get(k)
            if v is not None and v != "" and v != 0:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
            vd = dema_data.get(k)
            if vd is not None and vd != "" and vd != 0:
                try:
                    return float(vd)
                except (ValueError, TypeError):
                    pass
        return None

    rsi = extra_rsi if extra_rsi is not None else _val("rsi", "RSI", "rsi14", "RSI_14")
    volume = extra_volume if extra_volume is not None else _val("volume", "Volume", "last_volume")
    vol_int = int(volume) if volume and volume > 0 else None

    dema_20 = _val("dema_20", "DMA_20", "dma20", "DMA20", "20_DEMA")
    dema_50 = _val("dema_50", "DMA_50", "dma50", "DMA50", "50_DEMA")
    dema_100 = _val("dema_100", "DMA_100", "dma100", "DMA100", "100_DEMA")
    dema_200 = _val("dema_200", "DMA_200", "dma200", "DMA200", "200_DEMA")

    nifty = get_nifty_market_context()

    return {
        "rsi": round(rsi, 2) if rsi is not None else None,
        "volume": vol_int,
        "dema_20": round(dema_20, 2) if dema_20 is not None else None,
        "dema_50": round(dema_50, 2) if dema_50 is not None else None,
        "dema_100": round(dema_100, 2) if dema_100 is not None else None,
        "dema_200": round(dema_200, 2) if dema_200 is not None else None,
        "nifty_price": nifty.get("nifty_price"),
        "nifty_dema_20": nifty.get("nifty_dema_20"),
        "nifty_dema_50": nifty.get("nifty_dema_50"),
        "nifty_dema_100": nifty.get("nifty_dema_100"),
        "nifty_dema_200": nifty.get("nifty_dema_200")
    }
