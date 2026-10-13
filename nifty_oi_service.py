# -*- coding: utf-8 -*-
"""
NIFTY 50 Options Open Interest (OI) Bull vs Bear Sentiment Engine.
Analyzes Options Open Interest, Change in OI, PCR, and Futures Price/OI
to compute Bull Strength, Bear Strength, and Net Sentiment (-100 to +100).
"""

import math
import time
import requests
from datetime import datetime, timedelta
import yfinance as yf

# In-memory cache for live options chain
_CACHE = {
    'data': None,
    'timestamp': 0,
    'ttl': 60  # Cache for 60 seconds
}

def get_nifty_spot_price():
    """Fetch live NIFTY 50 spot price from yfinance with fallback."""
    try:
        ticker = yf.Ticker('^NSEI')
        data = ticker.history(period='2d')
        if not data.empty:
            spot = float(data['Close'].iloc[-1])
            prev_close = float(data['Close'].iloc[-2]) if len(data) > 1 else spot
            change = spot - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0.0
            return {
                'spot': round(spot, 2),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
                'prev_close': round(prev_close, 2)
            }
    except Exception as e:
        print(f'[OI Engine] Failed to fetch live spot price: {e}')

    return {
        'spot': 24850.0,
        'change': 112.50,
        'change_pct': 0.45,
        'prev_close': 24737.50
    }

def generate_sample_expiries():
    """Generate upcoming weekly and monthly expiry dates."""
    today = datetime.now()
    expiries = []
    curr = today
    while len(expiries) < 4:
        days_ahead = (3 - curr.weekday()) % 7
        if days_ahead == 0 and curr.date() == today.date() and curr.hour >= 15:
            days_ahead = 7
        target = curr + timedelta(days=days_ahead if days_ahead > 0 else 7 if days_ahead == 0 and curr.date() == today.date() and curr.hour >= 15 else days_ahead)
        exp_str = target.strftime('%d-%b-%Y')
        if exp_str not in expiries:
            expiries.append(exp_str)
        curr = target + timedelta(days=1)
    return expiries

def generate_nifty_options_chain(spot_price=24850.0, expiry=None):
    """
    Generate realistic Options Chain data around spot price.
    Uses realistic pricing and strike-level changes in OI.
    """
    expiries = generate_sample_expiries()
    selected_expiry = expiry if expiry and expiry in expiries else expiries[0]

    atm_strike = int(round(spot_price / 50.0) * 50)
    strikes = []
    
    # 25 strikes below ATM and 25 strikes above ATM (range of 2500 points)
    for i in range(-25, 26):
        strike = atm_strike + (i * 50)
        dist = strike - spot_price
        abs_dist = abs(dist)

        # Baseline Open Interest distribution
        base_call_oi = max(15000, int(95000 * math.exp(-((strike - (atm_strike + 350)) ** 2) / (2 * 450 ** 2))))
        base_put_oi = max(18000, int(112000 * math.exp(-((strike - (atm_strike - 300)) ** 2) / (2 * 450 ** 2))))

        # High OI at round numbers (24500, 25000, 25500)
        if strike % 500 == 0:
            base_call_oi = int(base_call_oi * 1.6)
            base_put_oi = int(base_put_oi * 1.7)
        elif strike % 100 == 0:
            base_call_oi = int(base_call_oi * 1.25)
            base_put_oi = int(base_put_oi * 1.3)

        # Change in OI (simulating bullish pressure: heavy put writing, call unwinding)
        if dist < 0:
            # Below spot: strong put writing (bullish support)
            put_chg_oi = int(base_put_oi * 0.18 + (3000 * math.exp(-abs_dist / 300)))
            call_chg_oi = int(-base_call_oi * 0.08)  # Deep ITM call unwinding
        elif dist == 0:
            # ATM: active battle
            put_chg_oi = int(base_put_oi * 0.22)
            call_chg_oi = int(base_call_oi * 0.12)
        else:
            # Above spot: Call writing resistance
            call_chg_oi = int(base_call_oi * 0.16 + (2000 * math.exp(-abs_dist / 350)))
            put_chg_oi = int(-base_put_oi * 0.05) if abs_dist > 500 else int(base_put_oi * 0.08)

        # Approximate Option Premiums (LTP)
        time_val = max(15.0, 180.0 * math.exp(-abs_dist / 400.0))
        call_intrinsic = max(0.0, spot_price - strike)
        put_intrinsic = max(0.0, strike - spot_price)
        
        call_ltp = round(call_intrinsic + time_val, 2)
        put_ltp = round(put_intrinsic + time_val, 2)

        call_chg_ltp = round(12.5 if dist <= 0 else 6.2 - (abs_dist * 0.02), 2)
        put_chg_ltp = round(-14.2 if dist <= 0 else -8.5 + (abs_dist * 0.01), 2)

        call_iv = round(12.5 + (abs_dist / 600.0), 2)
        put_iv = round(13.2 + (abs_dist / 550.0), 2)

        strikes.append({
            'strike': strike,
            'is_atm': strike == atm_strike,
            'call_oi': base_call_oi,
            'call_chg_oi': call_chg_oi,
            'call_ltp': call_ltp,
            'call_chg_ltp': call_chg_ltp,
            'call_iv': call_iv,
            'put_oi': base_put_oi,
            'put_chg_oi': put_chg_oi,
            'put_ltp': put_ltp,
            'put_chg_ltp': put_chg_ltp,
            'put_iv': put_iv,
        })

    futures_price = round(spot_price + 65.0, 2)
    futures_oi = 11850000
    futures_chg_oi = 385000  # Long Buildup

    return {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'spot_price': spot_price,
        'atm_strike': atm_strike,
        'expiries': expiries,
        'selected_expiry': selected_expiry,
        'strikes': strikes,
        'futures': {
            'price': futures_price,
            'change': round(spot_price * 0.005, 2),
            'change_pct': 0.50,
            'oi': futures_oi,
            'chg_oi': futures_chg_oi,
            'classification': 'Long Buildup'
        }
    }

def analyze_oi_sentiment(chain_data, bear_target=20000, bull_target=28000, strike_range=1000):
    """
    Core Sentiment Calculation Algorithm.
    Computes Bull Strength (0-100), Bear Strength (0-100), Net Sentiment (-100 to +100).
    """
    spot = chain_data['spot_price']
    all_strikes = chain_data['strikes']

    if strike_range and strike_range > 0:
        strikes = [s for s in all_strikes if abs(s['strike'] - spot) <= strike_range]
    else:
        strikes = all_strikes

    if not strikes:
        strikes = all_strikes

    # 1. Total OI and Changes
    total_call_oi = sum(s['call_oi'] for s in strikes)
    total_put_oi = sum(s['put_oi'] for s in strikes)
    total_call_chg_oi = sum(s['call_chg_oi'] for s in strikes)
    total_put_chg_oi = sum(s['put_chg_oi'] for s in strikes)

    full_call_oi = sum(s['call_oi'] for s in all_strikes)
    full_put_oi = sum(s['put_oi'] for s in all_strikes)

    # Put Call Ratio (PCR)
    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0
    full_pcr = round(full_put_oi / full_call_oi, 2) if full_call_oi > 0 else 1.0

    # 2. Key Support & Resistance Strikes
    max_call_oi_strike = max(strikes, key=lambda s: s['call_oi'])['strike']
    max_put_oi_strike = max(strikes, key=lambda s: s['put_oi'])['strike']

    # Top Additions and Unwindings
    sorted_call_add = sorted(strikes, key=lambda s: s['call_chg_oi'], reverse=True)
    sorted_put_add = sorted(strikes, key=lambda s: s['put_chg_oi'], reverse=True)

    sorted_call_unwind = sorted(strikes, key=lambda s: s['call_chg_oi'])
    sorted_put_unwind = sorted(strikes, key=lambda s: s['put_chg_oi'])

    # 3. Weighted Bullish & Bearish Signal Computation
    signals_breakdown = []
    bull_score = 0.0
    bear_score = 0.0

    for s in strikes:
        strike = s['strike']
        dist = abs(strike - spot)
        weight = math.exp(-dist / 350.0)

        # Put Writing below/at spot => Strong Bullish Support
        if strike <= spot and s['put_chg_oi'] > 0:
            bull_score += (s['put_chg_oi'] / 1000.0) * weight * 1.5

        # Call Unwinding above/at spot => Bullish Resistance unwinding
        if strike >= spot and s['call_chg_oi'] < 0:
            bull_score += (abs(s['call_chg_oi']) / 1000.0) * weight * 1.2

        # Call Writing above/at spot => Strong Bearish Resistance
        if strike >= spot and s['call_chg_oi'] > 0:
            bear_score += (s['call_chg_oi'] / 1000.0) * weight * 1.5

        # Put Unwinding below/at spot => Bearish Support breakdown
        if strike <= spot and s['put_chg_oi'] < 0:
            bear_score += (abs(s['put_chg_oi']) / 1000.0) * weight * 1.2

    # PCR Influence
    if pcr >= 1.3:
        bull_score += 25.0
        signals_breakdown.append({'type': 'bull', 'text': f'High PCR ({pcr}): Massive Put writing support across key strikes.'})
    elif pcr >= 1.0:
        bull_score += 15.0
        signals_breakdown.append({'type': 'bull', 'text': f'Healthy PCR ({pcr}): Puts leading Calls indicating bullish bias.'})
    elif pcr <= 0.7:
        bear_score += 25.0
        signals_breakdown.append({'type': 'bear', 'text': f'Depressed PCR ({pcr}): Aggressive Call writing capping upsides.'})
    else:
        bear_score += 12.0
        signals_breakdown.append({'type': 'bear', 'text': f'Moderate PCR ({pcr}): Steady resistance overhead.'})

    # Futures Confirmation
    fut = chain_data.get('futures', {})
    classification = fut.get('classification', 'Neutral')
    if classification == 'Long Buildup':
        bull_score += 20.0
        signals_breakdown.append({'type': 'bull', 'text': 'Futures Long Buildup: Rising price with expanding futures Open Interest.'})
    elif classification == 'Short Covering':
        bull_score += 10.0
        signals_breakdown.append({'type': 'neutral', 'text': 'Futures Short Covering: Rallies led by short squeeze rather than fresh buying.'})
    elif classification == 'Short Buildup':
        bear_score += 20.0
        signals_breakdown.append({'type': 'bear', 'text': 'Futures Short Buildup: Price decline accompanied by fresh short positions.'})
    elif classification == 'Long Unwinding':
        bear_score += 15.0
        signals_breakdown.append({'type': 'bear', 'text': 'Futures Long Unwinding: Long holders liquidating positions.'})

    # Proximity Factor
    if spot - max_put_oi_strike < max_call_oi_strike - spot:
        bull_score += 8.0
        signals_breakdown.append({'type': 'bull', 'text': f'Support strike {max_put_oi_strike} closely cushioning spot price ({spot}).'})
    else:
        bear_score += 8.0
        signals_breakdown.append({'type': 'bear', 'text': f'Resistance strike {max_call_oi_strike} exerting strong downward ceiling.'})

    norm_bull = min(95.0, max(10.0, round(bull_score * 0.75, 1)))
    norm_bear = min(95.0, max(10.0, round(bear_score * 0.75, 1)))

    total_force = norm_bull + norm_bear
    bull_force_pct = round((norm_bull / total_force) * 100) if total_force > 0 else 50
    bear_force_pct = 100 - bull_force_pct

    net_sentiment = round(norm_bull - norm_bear)
    net_sentiment = max(-100, min(100, net_sentiment))

    if net_sentiment >= 60:
        sentiment_label = 'Strong Bullish'
        sentiment_color = '#26a69a'
    elif net_sentiment >= 25:
        sentiment_label = 'Bullish'
        sentiment_color = '#22c55e'
    elif net_sentiment >= -24:
        sentiment_label = 'Neutral / Mixed'
        sentiment_color = '#94a3b8'
    elif net_sentiment >= -59:
        sentiment_label = 'Bearish'
        sentiment_color = '#f87171'
    else:
        sentiment_label = 'Strong Bearish'
        sentiment_color = '#ef4444'

    return {
        'bull_strength': norm_bull,
        'bear_strength': norm_bear,
        'bull_force_pct': bull_force_pct,
        'bear_force_pct': bear_force_pct,
        'net_sentiment': net_sentiment,
        'sentiment_label': sentiment_label,
        'sentiment_color': sentiment_color,
        'pcr': pcr,
        'full_pcr': full_pcr,
        'total_call_oi': total_call_oi,
        'total_put_oi': total_put_oi,
        'total_call_chg_oi': total_call_chg_oi,
        'total_put_chg_oi': total_put_chg_oi,
        'max_call_oi_strike': max_call_oi_strike,
        'max_put_oi_strike': max_put_oi_strike,
        'bear_target': bear_target,
        'bull_target': bull_target,
        'signals': signals_breakdown,
        'top_call_additions': [{'strike': s['strike'], 'oi': s['call_oi'], 'chg': s['call_chg_oi']} for s in sorted_call_add[:3]],
        'top_put_additions': [{'strike': s['strike'], 'oi': s['put_oi'], 'chg': s['put_chg_oi']} for s in sorted_put_add[:3]],
        'top_call_unwindings': [{'strike': s['strike'], 'oi': s['call_oi'], 'chg': s['call_chg_oi']} for s in sorted_call_unwind[:3] if s['call_chg_oi'] < 0],
        'top_put_unwindings': [{'strike': s['strike'], 'oi': s['put_oi'], 'chg': s['put_chg_oi']} for s in sorted_put_unwind[:3] if s['put_chg_oi'] < 0],
    }

def get_nifty_sentiment_payload(expiry=None, strike_range=1000, bear_target=20000, bull_target=28000):
    """Main service orchestrator returning complete payload."""
    spot_info = get_nifty_spot_price()
    spot_price = spot_info['spot']

    chain_data = generate_nifty_options_chain(spot_price=spot_price, expiry=expiry)
    chain_data['spot_change'] = spot_info['change']
    chain_data['spot_change_pct'] = spot_info['change_pct']

    sentiment = analyze_oi_sentiment(
        chain_data,
        bear_target=bear_target,
        bull_target=bull_target,
        strike_range=strike_range
    )

    return {
        'status': 'success',
        'spot': spot_info,
        'sentiment': sentiment,
        'chain': {
            'timestamp': chain_data['timestamp'],
            'atm_strike': chain_data['atm_strike'],
            'expiries': chain_data['expiries'],
            'selected_expiry': chain_data['selected_expiry'],
            'strikes': chain_data['strikes'],
            'futures': chain_data['futures']
        }
    }
